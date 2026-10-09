# osu_2_mgxc
converter from .osu (osu!mania) file to .mgxc file (Umiguri and Margrete)

thanks a lot to [OusPyPaser](https://github.com/lenforiee/osupyparser)

## Usage

```powershell
python osu_mania_to_mgxc.py <input_folder> <output_folder> [genre]
```

The converter processes `.osu` files directly inside the input folder and skips
charts that are not osu!mania. Mania charts are ranked by hit-object count:
`DIFFICULTY` starts at `0` for the chart with the fewest notes and increases by
one for each chart. Ties are ordered by filename. Each converted chart and its
copied media are placed in a subfolder named `<title> - <artist>` using the
non-Unicode metadata when available. An explicit `genre` argument takes
priority. When omitted or empty, the output folder name is used if its parent
is `music`; otherwise the genre defaults to `Jpop`.