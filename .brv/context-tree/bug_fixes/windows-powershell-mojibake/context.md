
When checking for mojibake on Windows/PowerShell, use Get-Content -Raw -Encoding utf8; default encoding can display valid UTF-8 text as garbled.
