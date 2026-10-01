# Red de ciclovías por Sistema

Visor web (MapLibre GL JS) que muestra cómo cada Sistema de ciclovías activa la red
de ciclovías existentes: tributarias directas, red alcanzable por km o por saltos,
fragmentos de red que se unen y brechas de conexión.

## Archivos

| Archivo | Qué es |
|---|---|
| `index.html` | El visor. Se abre con doble clic o se publica en GitHub Pages. |
| `config.js` | Configuración pública (mapa base inicial, Google). Se publica. |
| `config.local.js` | Claves privadas (token de Mapbox). Sólo local: está en `.gitignore` y no se sube. |
| `data/datos.js` | Datos del análisis de red (lo genera el script; no editar a mano). |
| `data/capas.js` | Capas de referencia del panel derecho (lo genera el script). |
| `procesamiento/procesar_red.py` | Script que calcula la activación de red y genera `data/datos.js`. |

## Actualizar los datos

1. Reemplazar el GeoJSON en `C:\Plan_Maestro\Geolibre\` (o cambiar la ruta en la
   sección CONFIGURACIÓN del script).
2. Ejecutar en PowerShell:

   ```
   python C:\Plan_Maestro\visor_red_ciclovias\procesamiento\procesar_red.py
   ```

3. Abrir `index.html` para revisar y volver a subir `data/datos.js` a GitHub.

Capas de referencia (PMC, factibilidad EVA, ciclovías proyectadas, La Chimba, Alameda T3, Mapocho
Pedaleable, ferias, pasos a desnivel, paraderos, siniestros): se definen en `CAPAS_REFERENCIA` del
script (ruta y campos a exportar) y su estilo/popup en `CAPAS_REF` de `index.html`.

Campos requeridos en la capa de sistemas: `Sistema`, `tipo`, `name`.
Las categorías se colorean según el texto de `tipo` ("Plan Maestro", "Extra",
"Existente", "Alternativa", "Planificado"); los tramos cuyo tipo contiene
"Alternativa" se muestran sólo con el trazado "Con alternativas".

## Publicar en GitHub Pages (sin instalar nada)

1. Crear una cuenta en https://github.com (si no tienes).
2. Botón **New repository** → nombre `visor-red-ciclovias` → **Public** → **Create repository**.
3. En el repositorio vacío: enlace **uploading an existing file** → arrastrar
   `index.html`, `config.js`, `README.md` y las carpetas `data` y `procesamiento` → **Commit changes**.
4. **Settings → Pages** → *Source*: **Deploy from a branch** → *Branch*: `main` / `(root)` → **Save**.
5. Esperar 1–2 minutos. La dirección queda en
   `https://<tu-usuario>.github.io/visor-red-ciclovias/`.

Para actualizar: en el repositorio, entrar a la carpeta `data` → **Add file → Upload files** →
arrastrar el nuevo `datos.js` → **Commit changes**. La página se actualiza sola en 1–2 minutos.

> Ojo: un repositorio público en GitHub Pages es visible para cualquiera que tenga el enlace.

## Mapas de Mapbox

Pegar un token público (`pk.…`) en `config.js` → `mapboxToken`. Se usa la Static Tiles API
(uso oficial; 200.000 teselas/mes gratis). En https://account.mapbox.com/access-tokens/ restringir
el token por URL a `https://<tu-usuario>.github.io` (y `http://localhost:8765` para pruebas locales).

## Mapas de Google sin clave (acceso no oficial)

`config.js` → `googleNoOficial: true` agrega Google mapa/satélite/híbrido/terreno usando las URLs
directas `mt0-3.google.com/vt/lyrs=...` (las mismas que usan complementos de QGIS o GeoLibre).
Google no autoriza ese uso en sus términos de servicio; para quitarlos basta cambiar a `false`
y volver a subir `config.js`. Si se completa `googleApiKey`, se usa la API oficial.

## Clave de Google (Street View y mapas base de Google)

Se pega en `config.js` (`googleApiKey`). Sin clave el visor funciona igual: Street View se abre en
una pestaña de Google Maps y los mapas base de Google aparecen deshabilitados.

En Google Cloud Console (APIs y servicios):
1. Habilitar **Maps Embed API** (Street View dentro del visor, sin costo) y **Map Tiles API** (mapas base de Google).
2. En **Credenciales → tu clave → Restricciones**:
   - Restricción de aplicación: **Sitios web (HTTP referrers)** → `https://<tu-usuario>.github.io/*`
   - Restricción de API: sólo las dos APIs anteriores.

La clave queda visible en el código de la página publicada; las restricciones son las que impiden
que otros la usen en otros sitios. Con la restricción por sitio web, la clave no funciona al abrir
`index.html` con doble clic (archivo local); para probar en local se puede usar una clave sin
restricción de sitio, y no subirla a GitHub.

## Método

- Sin corrección topológica: dos tramos están conectados si están a ≤ 15 m.
- Nivel 0: existentes superpuestos al sistema (forman parte de él).
- Nivel 1: existentes que tocan el sistema (tributarias directas); nivel 2: los que tocan a los de nivel 1, etc.
- Km por la red: distancia recorrida por ciclovías existentes desde el sistema hasta el inicio de cada tramo.
- Fragmentos unidos: componentes conexas de la red existente que quedan conectadas a través del sistema.
- Brechas: extremos sueltos a entre 15 y 300 m de otro tramo (a ≤ 3 km de algún sistema).
