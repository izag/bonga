setlocal enabledelayedexpansion

for /l %%i in (0, 1, 6) do (
	set /a "x = %%i * 233 - 38"
	for /l %%j in (0, 1, 1) do (
		set /a "y= %%j * 470 - 10"
		start C:\Users\Gregory\AppData\Local\Programs\Python\Python312\pythonw.exe C:\progs\bonga\bonga.py 265 390 !x! !y!
		timeout 1
	)
)
