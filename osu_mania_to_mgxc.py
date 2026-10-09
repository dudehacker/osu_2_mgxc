from osupyparser import OsuFile
import sys
from osupyparser.osu.objects import TimingPoint, HitObject
import re
import uuid
import shutil
from pathlib import Path
from typing import List, Dict, Tuple
from PIL import Image
KEY_CNT_TO_KEY_WIDTH_MAPPING = {
    1: {0: (0, 16)},
    2: {0: (0, 8), 1: (8, 8)},
    3: {0: (0, 4), 1: (4, 8), 2: (12, 4)},
    4: {0: (0, 4), 1: (4, 4), 2: (8, 4), 3: (12, 4)},
    5: {0: (0, 3), 1: (3, 3), 2: (6, 4), 3: (10, 3), 4: (13, 3)},
    6: {0: (0, 3), 1: (3, 2), 2: (5, 3), 3: (8, 3), 4: (11, 2), 5: (13, 3)},
    7: {0: (0, 2), 1: (2, 2), 2: (4, 2), 3: (6, 4), 4: (10, 2), 5: (12, 2), 6: (14, 2)},
    8: {0: (0, 2), 1: (2, 2), 2: (4, 2), 3: (6, 2), 4: (8, 2), 5: (10, 2), 6: (12, 2), 7: (14, 2)},
}


def pLine(*args):
    print(*args, sep='\t', file=ugcFile)


def pErr(*args):
    print(*args, file=sys.stderr)


LV_REGEX = re.compile(r'.*\[(\d\d?)\].*')
INVALID_FOLDER_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def getLevel(version):
    m = LV_REGEX.match(version)
    if m:
        return m[1]
    return '1'


def getFolderName(title, fallback):
    folderName = INVALID_FOLDER_CHARS.sub('_', title).strip().rstrip('.')
    return folderName or fallback


def getGenre(outputDir, genre):
    if genre and genre.strip():
        return genre.strip()
    if outputDir.parent.name.casefold() == 'music':
        return outputDir.name
    return 'Jpop'


def getBackgroundFilename(osuFilename, data):
    sourceDir = Path(osuFilename).resolve().parent
    videoFilename = data.video_file if data.has_video else ''
    if videoFilename:
        videoPath = Path(videoFilename)
        if (not videoPath.is_absolute() and '..' not in videoPath.parts and
                (sourceDir / videoPath).is_file()):
            return videoFilename
    return data.background_file


def createJacket(osuFilename, mgxcFilename, data):
    sourceDir = Path(osuFilename).resolve().parent
    backgroundPath = Path(data.background_file)
    if not data.background_file:
        pErr(f'WARNING: no background image found for {Path(osuFilename).name}')
        return ''
    if backgroundPath.is_absolute() or '..' in backgroundPath.parts:
        pErr(f'WARNING: skipping unsafe background path: {data.background_file}')
        return ''

    sourcePath = sourceDir / backgroundPath
    if not sourcePath.is_file():
        pErr(f'WARNING: background image not found: {sourcePath}')
        return ''

    imageExtension = sourcePath.suffix.lower()
    if imageExtension not in ('.jpg', '.jpeg', '.png'):
        pErr(f'WARNING: jacket image must be JPG or PNG: {sourcePath}')
        return ''

    mgxcPath = Path(mgxcFilename)
    jacketFilename = f'jacket{sourcePath.suffix}'
    jacketDirectory = mgxcPath.resolve().parent
    jacketPath = jacketDirectory / jacketFilename

    try:
        jacketDirectory.mkdir(parents=True, exist_ok=True)
        with Image.open(sourcePath) as image:
            width, height = image.size
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            jacket = image.crop((left, top, left + side, top + side))
            if imageExtension in ('.jpg', '.jpeg') and jacket.mode not in ('L', 'RGB'):
                jacket = jacket.convert('RGB')
            imageFormat = 'PNG' if imageExtension == '.png' else 'JPEG'
            jacket.save(jacketPath, format=imageFormat)
    except (OSError, ValueError) as error:
        pErr(f'WARNING: unable to create jacket from {sourcePath}: {error}')
        return ''

    return jacketFilename


def copyAssets(osuFilename, mgxcFilename, data):
    sourceDir = Path(osuFilename).resolve().parent
    outputDir = Path(mgxcFilename).resolve().parent
    backgroundFilename = getBackgroundFilename(osuFilename, data)
    if data.has_video and data.video_file and backgroundFilename != data.video_file:
        pErr(f'WARNING: video file not found: {data.video_file}')

    assets = [data.audio_filename, backgroundFilename]

    for assetFilename in assets:
        if not assetFilename:
            continue

        assetPath = Path(assetFilename)
        if assetPath.is_absolute() or '..' in assetPath.parts:
            pErr(f'WARNING: skipping unsafe asset path: {assetFilename}')
            continue

        sourcePath = sourceDir / assetPath
        outputPath = outputDir / assetPath
        if not sourcePath.is_file():
            pErr(f'WARNING: asset file not found: {sourcePath}')
            continue
        if sourcePath.resolve() == outputPath.resolve():
            continue

        outputPath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(sourcePath, outputPath)


BEAT_TICK_LEN = 480


def getUgcTimingSections(timePoints):
    orderedTimePoints = sorted(timePoints, key=lambda tp: tp.offset)
    if not orderedTimePoints:
        raise ValueError('osu! chart has no timing points')

    firstTimePoint = orderedTimePoints[0]
    sections = [(0, 0, firstTimePoint.time_signature)]
    sectionStartTick = 0
    sectionStartBar = 0
    currentSignature = firstTimePoint.time_signature

    for timePoint in orderedTimePoints[1:]:
        tick = max(0, round((timePoint.offset - firstTimePoint.offset) /
                            firstTimePoint.beat_length * BEAT_TICK_LEN))
        if timePoint.time_signature == currentSignature:
            continue

        ticksPerBar = currentSignature * BEAT_TICK_LEN
        elapsedTicks = tick - sectionStartTick
        bars, remainder = divmod(elapsedTicks, ticksPerBar)
        if remainder:
            pErr('WARNING: changing beat signature not at the beginning of a bar')
            bars = round(elapsedTicks / ticksPerBar)

        sectionStartBar += bars
        sectionStartTick = tick
        currentSignature = timePoint.time_signature
        sections.append((tick, sectionStartBar, currentSignature))

    return orderedTimePoints, sections


def timeToUgcPosition(time, firstTimePoint, sections):
    tick = max(0, round((time - firstTimePoint.offset) /
                        firstTimePoint.beat_length * BEAT_TICK_LEN))
    sectionStartTick, sectionStartBar, timeSignature = sections[0]
    for section in sections[1:]:
        if section[0] > tick:
            break
        sectionStartTick, sectionStartBar, timeSignature = section

    barLength = timeSignature * BEAT_TICK_LEN
    barOffset, tickInBar = divmod(tick - sectionStartTick, barLength)
    return f'{sectionStartBar + barOffset}\'{tickInBar}', tick


def printUgcTiming(timePoints, sections):
    bpms = {tp.bpm for tp in timePoints if tp.bpm is not None}
    if len(bpms) > 1:
        raise ValueError('cannot support changing of BPM')
    if not bpms:
        raise ValueError('osu! chart has no BPM timing point')

    firstTimePoint = timePoints[0]
    for _, startBar, timeSignature in sections:
        pLine('@BEAT', startBar, timeSignature, '4')

    for timePoint in timePoints:
        position, _ = timeToUgcPosition(
            timePoint.offset, firstTimePoint, sections)
        if timePoint.bpm is not None:
            pLine('@BPM', position, f'{timePoint.bpm:.5f}')
        if timePoint.velocity is not None:
            pLine('@TIL', '0', position, f'{timePoint.velocity:.5f}')

    mainBpm = next(tp.bpm for tp in timePoints if tp.bpm is not None)
    pLine('@MAINTIL', '0')
    pLine('@MAINBPM', f'{mainBpm:.5f}')


def printUgcNotes(timePoint1st, sections, hitObjects, keyCount):
    keyWidthMapping = KEY_CNT_TO_KEY_WIDTH_MAPPING[keyCount]

    for hitObject in hitObjects:
        osuKeyPos = hitObject.pos.x * keyCount // 512
        laneStart, laneWidth = keyWidthMapping[osuKeyPos]
        laneCode = f'{laneStart:X}{laneWidth:X}'
        position, startTick = timeToUgcPosition(
            hitObject.start_time, timePoint1st, sections)

        if hitObject.type & 1:
            pLine(f'#{position}:t{laneCode}')
            continue

        pLine(f'#{position}:s{laneCode}')
        endTick = timeToUgcPosition(
            int(hitObject.additions.normal), timePoint1st, sections)[1]
        pLine(f'#{endTick - startTick}>s{laneCode}')


def osuManiaToUgc(osuFilename, ugcFilename, difficulty, data=None, genre='Jpop'):
    if data is None:
        data = OsuFile(osuFilename).parse_file()
    jacketFilename = createJacket(osuFilename, ugcFilename, data)
    copyAssets(osuFilename, ugcFilename, data)
    timePoints, sections = getUgcTimingSections(data.timing_points)
    firstTimePoint = timePoints[0]
    previewStart = data.preview_time / 1000
    previewEnd = previewStart + 20

    artistUnicode = data.artist_unicode
    if data.source:
        artistUnicode = f'{artistUnicode} [{data.source}]'.strip()

    pLine("' Created by osu_2_mgxc")
    pLine('@VER', '8')
    pLine('@EXVER', '1')
    pLine('@TITLE', data.title_unicode)
    pLine('@SORT', data.title)
    pLine('@ARTIST', artistUnicode)
    pLine('@GENRE', genre)
    pLine('@DESIGN', data.creator)
    pLine('@DIFF', difficulty)
    pLine('@LEVEL', getLevel(data.version))
    pLine('@CONST', f'{float(getLevel(data.version)):.5f}')
    pLine('@SONGID', f'MGCF{uuid.uuid4().hex.upper()}')
    pLine('@BGM', data.audio_filename)
    pLine('@BGMOFS', f'{-firstTimePoint.offset / 1000:.5f}')
    pLine('@BGMPRV', f'{previewStart:.5f}', f'{previewEnd:.5f}')
    pLine('@JACKET', jacketFilename)
    pLine('@BGIMG', getBackgroundFilename(osuFilename, data))
    pLine('@BGMODE', 'PASSIVE', 'FALSE')
    pLine('@FLDCOL', '-1')
    pLine('@FLDIMG', '')
    pLine('@FLAG', 'DIFFTTL', 'FALSE')
    pLine('@FLAG', 'SOFFSET', 'TRUE')
    pLine('@FLAG', 'CLICK', 'TRUE')
    pLine('@FLAG', 'EXLONG', 'FALSE')
    pLine('@FLAG', 'BGMWCMP', 'FALSE')
    pLine('@FLAG', 'HIPRECISION', 'TRUE')
    pLine('@ATINFO', 'AUTHORS', '')
    pLine('@ATINFO', 'SITES', '')
    pLine('@DLURL', '')
    pLine('@COPYRIGHT', '')
    pLine('@LICENSE', '', '')
    pLine('@TICKS', BEAT_TICK_LEN)
    printUgcTiming(timePoints, sections)
    pLine('@ENDHEAD')
    printUgcNotes(firstTimePoint, sections, data.hit_objects, int(data.cs))


def convertFolder(inputFolder, outputFolder, genre=None):
    inputPath = Path(inputFolder)
    outputDir = Path(outputFolder)
    genre = getGenre(outputDir, genre)
    if inputPath.is_file():
        if inputPath.suffix.lower() != '.osu':
            raise ValueError(f'input file must have a .osu extension: {inputPath}')
        osuFiles = [inputPath]
    elif inputPath.is_dir():
        osuFiles = sorted(
            (path for path in inputPath.iterdir()
             if path.is_file() and path.suffix.lower() == '.osu'),
            key=lambda path: path.name.casefold())
    else:
        raise FileNotFoundError(inputPath)

    charts = []
    for osuPath in osuFiles:
        data = OsuFile(str(osuPath)).parse_file()
        if data.mode != 3:
            pErr(f'Skipping non-mania chart: {osuPath.name}')
            continue
        charts.append((osuPath, data))

    charts.sort(key=lambda chart: (len(chart[1].hit_objects),
                                   chart[0].name.casefold()))
    if not charts:
        pErr(f'No osu!mania charts found in {inputPath}')
        return

    outputDir.mkdir(parents=True, exist_ok=True)
    global ugcFile
    for difficulty, (osuPath, data) in enumerate(charts):
        songTitle = data.title or data.title_unicode or 'Untitled'
        songArtist = data.artist or data.artist_unicode
        songFolderName = f'{songTitle} - {songArtist}' if songArtist else songTitle
        songDir = outputDir / getFolderName(songFolderName, 'Untitled')
        songDir.mkdir(parents=True, exist_ok=True)
        ugcPath = songDir / f'{osuPath.stem}.ugc'
        with ugcPath.open('w', newline='', encoding='utf-8') as f:
            ugcFile = f
            osuManiaToUgc(osuPath, ugcPath, difficulty, data, genre)
        print(f'Converted {osuPath.name}: DIFFICULTY {difficulty}, '
              f'{len(data.hit_objects)} notes')


ugcFile = sys.stdout

if __name__ == '__main__':
    if len(sys.argv) not in (3, 4):
        raise ValueError(
            'usage: osu_mania_to_mgxc.py <input_folder_or_osu_file> '
            '<output_folder> [genre]')
    genre = sys.argv[3] if len(sys.argv) == 4 else None
    convertFolder(sys.argv[1], sys.argv[2], genre)

a = [
    TimingPoint(
        offset=169.0, beat_length=451.127819548872,
        time_signature=4, sample_set_id=2, custom_sample_index=0,
        sample_volume=5, timing_change=True, kiai_time_active=False,
        velocity=1, bpm=133),
    TimingPoint(offset=61523.0, beat_length=-133.333333333333, time_signature=2,
                sample_set_id=2, custom_sample_index=0, sample_volume=5, timing_change=False,
                kiai_time_active=False, velocity=0.7500000000000019, bpm=None),
    TimingPoint(offset=63328.0, beat_length=-100.0, time_signature=4, sample_set_id=2, custom_sample_index=0, sample_volume=5, timing_change=False, kiai_time_active=False,
                velocity=1.0, bpm=None)]
