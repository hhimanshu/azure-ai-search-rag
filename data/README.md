# Demo corpus — US state driver's manuals

Public domain (works of US state governments). Downloaded 2026-08-28.
Re-fetch with `./download.sh`. Do not commit the PDFs to git.

| File | State | Pages | Source |
|---|---|---|---|
| california-driver-handbook.pdf | California | 92 | dmv.ca.gov |
| florida-driver-handbook.pdf | Florida | 104 | flhsmv.gov |
| newjersey-driver-manual.pdf | New Jersey | 243 | nj.gov/mvc |
| virginia-drivers-manual.pdf | Virginia | 40 | dmv.virginia.gov |
| wisconsin-motorists-handbook.pdf | Wisconsin | 64 | wisconsindot.gov |

## Blob layout for the demo

One container, one virtual folder per state, so `metadata_storage_path`
yields a filterable `state` field with no custom skill:

    docs/california/california-driver-handbook.pdf
    docs/florida/florida-driver-handbook.pdf
    docs/new-jersey/newjersey-driver-manual.pdf
    docs/virginia/virginia-drivers-manual.pdf
    docs/wisconsin/wisconsin-motorists-handbook.pdf
