setlocal enabledelayedexpansion

for /l %%i in (0, 1, 4) do (
	set /a "x = %%i * 233 - 38"
	for /l %%j in (0, 1, 3) do (
		set /a "y= %%j * 410 - 10"
		start C:\Users\boy\AppData\Local\Programs\Python\Python311\\pythonw.exe C:\progs\bonga\bonga.py 265 390 !x! !y!
		timeout 1
	)
)

for /l %%i in (5, 1, 8) do (
	set /a "x = %%i * 233 - 38"
	for /l %%j in (0, 1, 7) do (
		set /a "y= %%j * 210 - 10"
		start C:\Users\boy\AppData\Local\Programs\Python\Python311\\pythonw.exe C:\progs\bonga\bonga.py 265 390 !x! !y!
		timeout 1
	)
)
