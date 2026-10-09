# osu_2_mgxc
converter from .osu (osu!mania) file to .mgxc file (Umiguri and Margrete)

thanks a lot to [OusPyPaser](https://github.com/lenforiee/osupyparser)

## Usage

Install the image-processing dependency first:

```powershell
python -m pip install -r requirements.txt
```

```powershell
python osu_mania_to_mgxc.py <input_folder_or_osu_file> <output_folder> [genre]
```

The input can be a folder or one `.osu` file. Folder input processes `.osu`
files directly inside that folder; file input converts only that chart. Charts
that are not osu!mania are skipped. Mania charts are ranked by hit-object count:
`DIFFICULTY` starts at `0` for the chart with the fewest notes and increases by
one for each chart. Ties are ordered by filename. Each converted chart and its
copied media are placed in a subfolder named `<title> - <artist>` using the
non-Unicode metadata when available. An explicit `genre` argument takes
priority. When omitted or empty, the output folder name is used if its parent
is `music`; otherwise the genre defaults to `Jpop`.

Each chart's JPG or PNG background is center-cropped to a square for its
jacket. The source extension is preserved, and the result is stored as
`jacket.<extension>` in the song's output folder.

Each generated `.mgxc` is also converted to a sibling `.ugc` file using
Margrete's `ugctool`. The tool must be on `PATH`, available in a `Margrete*`
folder above the output directory, or specified with `UGCTOOL_PATH`.