// Configuración del visor.
window.CONFIG = {
  // Clave de Google (API oficial). Si se completa, los mapas de Google y Street View integrado usan la API oficial.
  // APIs a habilitar en la clave: "Maps Embed API" (Street View) y "Map Tiles API" (mapas base).
  googleApiKey: "",

  // Mapas de Google SIN clave, con las URLs directas que usan QGIS/GeoLibre (acceso NO oficial).
  // Google no autoriza este uso en sus términos de servicio. Para quitarlos del visor: cambiar true por false.
  // (Si hay googleApiKey, se usa la API oficial y esta opción se ignora.)
  googleNoOficial: true,

  // Token público de Mapbox (empieza con "pk."). Si se completa, aparece el grupo Mapbox en el menú de mapas base.
  // Para usarlo sólo en tu computador, ponlo en config.local.js (no se publica).
  // Crear en https://account.mapbox.com/access-tokens/ y restringirlo por URL al sitio publicado.
  mapboxToken: "",

  // Mapa base al abrir el visor: carto-claro, osm, cyclosm, s2,
  // esri-satelite, esri-hibrido, esri-calles, esri-topo, esri-gris, esri-gris-osc,
  // mapbox-calles, mapbox-claro, mapbox-oscuro, mapbox-outdoors, mapbox-satelite, mapbox-sat-calles,
  // google-mapa, google-satelite, google-hibrido, google-terreno
  mapaBaseInicial: "carto-claro",
};
