@echo off
rem Abre el visor desde un servidor local (http://localhost) en vez de doble clic en index.html.
rem Así el navegador se identifica ante OpenStreetMap y Google y los mapas base cargan.
rem Para cerrar el visor: cerrar esta ventana negra.
cd /d "%~dp0"
echo Visor de red de ciclovias en http://localhost:8765
echo Cierra esta ventana para detener el visor.
start "" "http://localhost:8765/index.html"
python -m http.server 8765 --bind 127.0.0.1
pause
