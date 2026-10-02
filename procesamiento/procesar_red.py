"""
Calcula la "activación de red" de cada Sistema de ciclovías sobre la red existente
y genera data/datos.js para el visor (index.html).

Uso:  python procesar_red.py
(editar las rutas de CONFIGURACIÓN si cambian los archivos de entrada)

Método (sin corrección topológica):
  - Dos tramos se consideran conectados si están a <= TOLERANCIA_M metros.
  - Nivel 0: tramos existentes que forman parte del propio sistema (superpuestos).
  - Nivel 1: existentes que tocan el sistema (tributarios directos); nivel 2: los que
    tocan a los de nivel 1; etc. (saltos de red).
  - Distancia de red: km recorridos por la red existente desde el sistema hasta el
    inicio de cada tramo.
  - Efecto red: fragmentos de red existente (componentes conexas) que el sistema une.
  - Brechas: extremos sueltos a entre TOLERANCIA_M y BRECHA_MAX_M de otro tramo.
"""
import json
import heapq
from itertools import combinations
from datetime import date
from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import pandas as pd
from shapely.geometry import Point
from shapely import shortest_line

# ---------------------------------------------------------------- CONFIGURACIÓN
ENTRADA = Path(r"C:\Plan_Maestro\Geolibre")
SISTEMAS = ENTRADA / "sistemas_ciclovias_propuesta.geojson"
EXISTENTES = ENTRADA / "ciclovias_existentes_jul26.geojson"
CAMPO_SISTEMA = "Sistema"
CAMPO_TIPO = "tipo"
CAMPO_NOMBRE = "name"

TOLERANCIA_M = 15        # distancia para considerar dos tramos conectados
BRECHA_MAX_M = 300       # brechas más largas no se consideran
SOLAPE_SISTEMA = 0.5     # fracción de un existente dentro del sistema para ser "nivel 0"
RADIO_BRECHAS_M = 3000   # sólo se exportan brechas a esta distancia de algún sistema

SALIDA = Path(__file__).resolve().parent.parent / "data" / "datos.js"
SALIDA_CAPAS = SALIDA.parent / "capas.js"

# Capas de referencia (sólo visualización, no entran en el cálculo de red) -> data/capas.js.
# id: nombre interno usado por el visor; campos: atributos que se exportan para los popups;
# derivar: función opcional que agrega campos calculados (se define más abajo).
CAPAS_REFERENCIA = [
    {"id": "pmc_metro", "archivo": ENTRADA / "PMC_Metropolitanos.geojson",
     "campos": ["nombre", "cod", "km", "tramo_RS", "inicio", "termino", "esttado"]},
    {"id": "pmc_ci", "archivo": ENTRADA / "PMC_Comunales_Intercomunales.geojson",
     "campos": ["nombre", "COD_EJE", "escala", "km", "comunas", "macrozona", "anteproyec"]},
    {"id": "eva", "archivo": ENTRADA / "factibilidad_EVA_112026.geojson",
     "campos": ["rank", "id", "nombre", "escala", "macrozona", "comunas", "km", "costo_total_MCLP", "score",
                "factibilidad", "num_pistas", "pend_media_pct", "pend_max_pct", "explicacion"]},
    {"id": "proyectadas", "archivo": ENTRADA / "ciclovias_proyctadas_otrascarteras_jul26.geojson",
     "campos": ["EJE_VIA", "COMUNA", "INICIO", "FIN", "KM", "TIPO", "CARAC_FUNC", "ETAPA", "Etapa_det", "CARTERA",
                "NOMBRE_PRO", "NORMATIVA"]},
    {"id": "chimba", "archivo": ENTRADA / "Chimba.geojson",
     "campos": ["Eje", "Tramo", "estado", "CateVial", "SentTransi", "NPistas", "km"]},
    {"id": "alameda_t3", "archivo": ENTRADA / "Alameda_tramo3.geojson",
     "campos": ["EJE_VIA", "COMUNA", "INICIO", "FIN", "CARAC_FUNC", "ETAPA_DET", "CARTERA", "NORMATIVA"]},
    {"id": "mapocho", "archivo": ENTRADA / "Mapocho_pedaleable.geojson", "campos": []},
    {"id": "ferias", "archivo": ENTRADA / "ferias_libres_persas_RM.geojson", "derivar": lambda g: derivar_ferias(g),
     "campos": ["nombre", "comuna", "tipo", "diasTexto", "horario", "ubic", "puestos", "relCiclovia"]},
    {"id": "pasos", "archivo": ENTRADA / "Pasos_bajo_sobre_nivel_tuneles.geojson", "derivar": lambda g: derivar_pasos(g),
     "campos": ["name", "estructura", "vía"]},
    {"id": "paraderos", "archivo": ENTRADA / "paraderos_bus_GTFS.json", "campos": [], "decimales": 5},
    {"id": "comunas", "archivo": ENTRADA / "comunas.geojson", "campos": ["COMUNA", "PROVINCIA", "CUT"],
     "simplificar": 10, "decimales": 5},   # límites comunales: basta precisión de ~10 m
    {"id": "siniestros", "archivo": ENTRADA / "siniestros_bicicleta_2020_2024_RM.geojson", "decimales": 5,
     "derivar": lambda g: derivar_siniestros(g),
     "campos": ["anio", "comuna", "tipo", "tipo_grupo", "causa", "lugar", "ubic", "severidad", "peso",
                "fall", "grav", "meng", "leve"]},
]

# Colores y estilo por categoría de tramo (se asignan por coincidencia de texto en
# el campo tipo, en este orden; los tipos no reconocidos toman los colores de RESERVA).
# trazo: "continuo", "guiones" o "puntos". Simbología acordada (igual a la leyenda de QGIS).
# El orden de esta lista es el orden de la leyenda; la definición se muestra como glosario.
ESTILO_TIPOS = [
    # (texto a buscar, etiqueta, color, trazo, definición)
    ("con diseño", "Con diseño", "#b48ee6", "continuo", "Ciclovía ya cuenta con diseño"),
    ("en diseño", "En diseño", "#b48ee6", "puntos", "Ciclovía en etapa de diseño"),
    ("priorizado", "Eje PMC priorizado", "#2eb82e", "continuo", "Ciclovía perteneciente al PMC priorizado por EVA"),
    ("no evaluado", "Eje PMC no evaluado", "#2eb82e", "puntos",
     "Ciclovía perteneciente al PMC cuya factibilidad no ha sido evaluada"),
    ("existente", "Existente", "#1b2f7a", "continuo",   # azul marino: distinto de la red existente/activada
     "Ciclovía existente (a evaluar su requerimiento de normalización)"),
    ("propuesta", "Propuesta", "#f2c200", "continuo",
     "Ciclovía no pertenece a PMC y se propone para dar conectividad al sistema"),
    ("planificad", "Planificado", "#eb6834", "continuo", ""),
    ("alternativ", "Alternativa", "#e87ba4", "guiones", ""),
]
# Textos de "tipo" que se tratan como trazado alternativo (se muestran sólo con "Con alternativas",
# en línea discontinua). Ej.: ["alternativ", "propuesta"]
TIPOS_ALTERNATIVA = ["alternativ"]
RESERVA = ["#4a3aa7", "#1baf7a", "#898781"]
# ------------------------------------------------------------------------------


def es_alternativa(tipo):
    return any(t in str(tipo).lower() for t in TIPOS_ALTERNATIVA)


def es_existente(tipo):
    return "existente" in str(tipo).lower()


def orden_tipo(t):
    """Posición de la categoría en ESTILO_TIPOS (orden de la leyenda)."""
    tl = str(t).lower()
    return next((i for i, e in enumerate(ESTILO_TIPOS) if e[0] in tl), len(ESTILO_TIPOS))


def estilo_tipos(tipos):
    out, reserva = {}, list(RESERVA)
    for t in tipos:
        tl = str(t).lower()
        for clave, etiqueta, color, trazo, definicion in ESTILO_TIPOS:
            if clave in tl:
                out[t] = {"etiqueta": etiqueta, "color": color, "trazo": trazo, "definicion": definicion}
                break
        else:
            out[t] = {"etiqueta": str(t), "color": reserva.pop(0) if reserva else "#898781",
                      "trazo": "guiones" if es_alternativa(t) else "continuo", "definicion": ""}
    return out


def pares_cercanos(geoms_a, gdf_b, tol):
    """Pares (i, j) con geoms_a[i] a <= tol de gdf_b[j]."""
    ia, ib = gdf_b.sindex.query(geoms_a, predicate="dwithin", distance=tol)
    return list(zip(ia.tolist(), ib.tolist()))


def main():
    sis = gpd.read_file(SISTEMAS)
    ex = gpd.read_file(EXISTENTES)
    crs = sis.crs if sis.crs and sis.crs.is_projected else "EPSG:32719"
    sis = sis.to_crs(crs).reset_index(drop=True)
    ex = ex.to_crs(crs).reset_index(drop=True)
    sis = sis[sis.geometry.notna() & ~sis.geometry.is_empty].reset_index(drop=True)
    ex = ex[ex.geometry.notna() & ~ex.geometry.is_empty].reset_index(drop=True)
    ex["km_calc"] = ex.geometry.length / 1000
    sis["km_calc"] = sis.geometry.length / 1000
    if CAMPO_NOMBRE not in sis.columns:   # la capa de sistemas puede no traer nombre de tramo
        sis[CAMPO_NOMBRE] = None

    # --- Grafo de la red existente (tramos = nodos, cercanía <= tol = aristas)
    g_ex = nx.Graph()
    g_ex.add_nodes_from(range(len(ex)))
    for i, j in pares_cercanos(ex.geometry, ex, TOLERANCIA_M):
        if i < j:
            g_ex.add_edge(i, j)
    comp = {}
    comps = sorted(nx.connected_components(g_ex), key=len, reverse=True)
    for cid, c in enumerate(comps):
        for n in c:
            comp[n] = cid
    ex["comp"] = ex.index.map(comp)
    comp_km = ex.groupby("comp")["km_calc"].sum()
    ex["comp_km"] = ex["comp"].map(comp_km).round(2)
    print(f"Red existente: {len(ex)} tramos, {len(comps)} fragmentos (tol {TOLERANCIA_M} m)")

    # --- Escenarios: cada sistema y "todos" (se consideran todos los tramos de cada sistema)
    nombres = list(dict.fromkeys(sis[CAMPO_SISTEMA].dropna().tolist()))
    sistemas = [{"key": f"s{k + 1}", "nombre": n} for k, n in enumerate(nombres)]
    sistemas.append({"key": "all", "nombre": "Todos los sistemas"})
    sis["skey"] = sis[CAMPO_SISTEMA].map({s["nombre"]: s["key"] for s in sistemas})

    stats = {}
    for s in sistemas:
        sel = sis if s["key"] == "all" else sis[sis["skey"] == s["key"]]
        key = s["key"]
        hop, dist, st = activar(sel, ex, g_ex)
        ex[f"h_{key}"] = ex.index.map(hop)
        ex[f"d_{key}"] = ex.index.map(lambda i: round(dist[i], 2) if i in dist else None)
        stats[key] = st
        print(f"  {s['nombre']:30s} nivel1={st['km_nivel1']:6.1f} km  "
              f"fragmentos unidos={st['fragmentos_unidos']:3d}  "
              f"red conectada={st['km_red_conectada']:7.1f} km (mayor previa {st['km_mayor_previa']:.1f})")

    # Combinaciones de 2 o más sistemas (sólo indicadores; los niveles por tramo se combinan en el visor
    # tomando el mínimo entre los sistemas elegidos). Clave: s1+s3, en el orden de `sistemas`.
    claves = [s["key"] for s in sistemas if s["key"] != "all"]
    for r in range(2, len(claves)):
        for combo in combinations(claves, r):
            stats["+".join(combo)] = activar(sis[sis["skey"].isin(combo)], ex, g_ex)[2]
    print(f"Indicadores calculados para {len(stats)} combinaciones de sistemas")

    brechas = calcular_brechas(sis, ex)
    print(f"Brechas exportadas: {len(brechas)}")

    # --- Exportar
    tipos = list(dict.fromkeys(sis[CAMPO_TIPO].fillna("Sin tipo").tolist()))
    sis[CAMPO_TIPO] = sis[CAMPO_TIPO].fillna("Sin tipo")
    sis_out = sis[[CAMPO_NOMBRE, CAMPO_TIPO, CAMPO_SISTEMA, "skey", "km_calc", "geometry"]].rename(
        columns={CAMPO_NOMBRE: "nombre", CAMPO_TIPO: "tipo", CAMPO_SISTEMA: "sistema", "km_calc": "km"})
    estilos = estilo_tipos(tipos)
    sis_out["trazo"] = sis_out["tipo"].map(lambda t: estilos[t]["trazo"])
    sis_out["km"] = sis_out["km"].round(2)

    cols_ex = [c for c in ["IDENTIFICA", "EJE_VIA", "COMUNA", "INICIO", "FIN", "TIPO", "CARAC_FUNC",
                           "EMPLAZA_TE", "CARTERA", "YEAR_EJECU"] if c in ex.columns]
    cols_esc = [c for c in ex.columns if c[:2] in ("h_", "d_")]
    ex_out = ex[cols_ex + ["km_calc", "comp", "comp_km"] + cols_esc + ["geometry"]].rename(columns={"km_calc": "km"})
    ex_out["km"] = ex_out["km"].round(2)

    datos = {
        "generado": date.today().isoformat(),
        "tolerancia_m": TOLERANCIA_M,
        "brecha_max_m": BRECHA_MAX_M,
        "red_existente": {"tramos": len(ex), "km": round(ex.km_calc.sum(), 1), "fragmentos": len(comps)},
        "sistemas": sistemas,
        "tipos": [{"tipo": t, **estilos[t]} for t in sorted(tipos, key=lambda t: orden_tipo(t))],
        "stats": stats,
        "geo": {"sistemas": a_geojson(sis_out), "existentes": a_geojson(ex_out), "brechas": a_geojson(brechas)},
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text("window.DATOS = " + json.dumps(datos, ensure_ascii=False, separators=(",", ":")) + ";\n",
                      encoding="utf-8")
    print(f"OK -> {SALIDA} ({SALIDA.stat().st_size / 1e6:.1f} MB)")
    exportar_referencia(crs)


def exportar_referencia(crs):
    """Capas de referencia -> data/capas.js (window.CAPAS = {id: GeoJSON})."""
    capas = {}
    for c in CAPAS_REFERENCIA:
        if not Path(c["archivo"]).exists():
            print(f"AVISO: no existe {c['archivo']}, se omite la capa {c['id']}")
            continue
        g = gpd.read_file(c["archivo"]).to_crs(crs)
        g = g[g.geometry.notna() & ~g.geometry.is_empty].copy()
        if c.get("derivar"):
            g = c["derivar"](g)
        g = g[[k for k in c.get("campos", []) if k in g.columns] + ["geometry"]]
        if "km" in g.columns:
            g["km"] = pd.to_numeric(g["km"], errors="coerce").round(2)
        if g.geom_type.str.contains("Line").any():
            g["km_geom"] = (g.geometry.length / 1000).round(3)   # largo medido (para totales)
        capas[c["id"]] = a_geojson(g, decimales=c.get("decimales", 6), simplificar=c.get("simplificar", 1.0))
        print(f"Capa de referencia {c['id']}: {len(g)} elementos")
    SALIDA_CAPAS.write_text("window.CAPAS = " + json.dumps(capas, ensure_ascii=False, separators=(",", ":")) + ";\n",
                            encoding="utf-8")
    print(f"OK -> {SALIDA_CAPAS} ({SALIDA_CAPAS.stat().st_size / 1e6:.1f} MB)")
    marcar_version()


def marcar_version():
    """Pone ?v=<fecha-hora> a los archivos de datos en index.html, para que el navegador no use una copia vieja."""
    import re
    from datetime import datetime
    index = SALIDA.parent.parent / "index.html"
    v = datetime.now().strftime("%Y%m%d%H%M")
    html = index.read_text(encoding="utf-8")
    nuevo = re.sub(r'src="data/(datos|capas)\.js(\?v=\d+)?"', rf'src="data/\1.js?v={v}"', html)
    if nuevo != html:
        index.write_text(nuevo, encoding="utf-8", newline="")
        print(f"Versión de datos en index.html: {v}")


def derivar_pasos(g):
    """Tipo de estructura a partir de other_tags de OSM."""
    t = g["other_tags"].fillna("")
    g["estructura"] = np.select(
        [t.str.contains('"tunnel"=>"(?:yes|building_passage|culvert)"', regex=True), t.str.contains('"bridge"=>', regex=False)],
        ["Túnel / paso bajo nivel", "Puente / paso sobre nivel"], "Otro desnivel")
    g["vía"] = g["highway"].map({"motorway": "Autopista", "motorway_link": "Enlace de autopista", "trunk": "Troncal",
                                 "primary": "Primaria", "primary_link": "Enlace primaria", "secondary": "Secundaria",
                                 "secondary_link": "Enlace secundaria", "tertiary": "Terciaria", "tertiary_link": "Enlace terciaria",
                                 "residential": "Residencial", "unclassified": "Local"}).fillna(g["highway"])
    return g


def derivar_siniestros(g):
    """Agrupa los 21 tipos de siniestro de Carabineros en 7 categorías."""
    grupos = {
        "Colisión lateral": ["COLISION LATERAL", "CHOQUE LATERAL", "CHOQUE LADO/LADO", "CHOQUE LADO/FRENTE",
                             "CHOQUE FRENTE/LADO", "CHOQUE LADO/POSTERIOR", "CHOQUE POSTERIOR/LADO"],
        "Colisión frontal": ["COLISION FRONTAL", "CHOQUE FRONTAL", "CHOQUE FRENTE/FRENTE"],
        "Colisión por alcance": ["COLISION POR ALCANCE", "CHOQUE FRENTE/POSTERIOR", "CHOQUE POSTERIOR/FRENTE",
                                 "CHOQUE POSTERIOR/POSTERIOR", "CHOQUE POSTERIOR"],
        "Colisión perpendicular": ["COLISION PERPENDICULAR"],
        "Volcadura / caída": ["VOLCADURA"],
        "Atropello": ["ATROPELLO"],
    }
    mapa = {t: grp for grp, ts in grupos.items() for t in ts}
    g["tipo_grupo"] = g["tipo"].str.strip().str.upper().map(mapa).fillna("Otro / sin especificar")
    return g


def derivar_ferias(g):
    g["horario"] = g["inicio"].fillna("?").astype(str) + " – " + g["levante"].fillna("?").astype(str)
    return g


def activar(sel, ex, g_ex):
    """Niveles (saltos) y distancia de red desde el sistema `sel` sobre la red existente."""
    if sel.empty:
        return {}, {}, vacio()
    union = sel.geometry.union_all()
    zona = union.buffer(TOLERANCIA_M)

    toca = set(j for _, j in pares_cercanos(sel.geometry, ex, TOLERANCIA_M))
    hop, dist = {}, {}
    for j in toca:
        g = ex.geometry.iloc[j]
        solape = g.intersection(zona).length / g.length if g.length else 0
        hop[j] = 0 if solape >= SOLAPE_SISTEMA else 1
        dist[j] = 0.0

    # Saltos (BFS)
    cola = sorted(toca, key=lambda j: hop[j])
    frente = list(cola)
    while frente:
        nuevo = []
        for i in frente:
            for j in g_ex.neighbors(i):
                if j not in hop:
                    hop[j] = max(hop[i], 1) + (0 if hop[i] == 0 else 1)
                    nuevo.append(j)
        frente = nuevo

    # Distancia de red (Dijkstra; costo = largo del tramo que se recorre)
    km = ex["km_calc"].values
    heap = [(0.0, j) for j in toca]
    heapq.heapify(heap)
    while heap:
        d, i = heapq.heappop(heap)
        if d > dist.get(i, np.inf):
            continue
        paso = 0.0 if hop.get(i) == 0 else km[i]
        for j in g_ex.neighbors(i):
            nd = d + paso
            if nd < dist.get(j, np.inf):
                dist[j] = nd
                heapq.heappush(heap, (nd, j))

    # Efecto red: grafo existente + tramos del sistema
    g = g_ex.copy()
    sid = [("s", k) for k in range(len(sel))]
    g.add_nodes_from(sid)
    for k, j in pares_cercanos(sel.geometry, ex, TOLERANCIA_M):
        g.add_edge(("s", k), j)
    for a, b in pares_cercanos(sel.geometry, sel.reset_index(drop=True), TOLERANCIA_M):
        if a < b:
            g.add_edge(("s", a), ("s", b))
    comps_sis = [c for c in nx.connected_components(g) if any(isinstance(n, tuple) for n in c)]
    km_nuevos = sel.loc[~sel[CAMPO_TIPO].map(es_existente), "km_calc"].sum()
    frag, km_red, km_mayor = set(), 0.0, 0.0
    for c in comps_sis:
        ex_n = [n for n in c if not isinstance(n, tuple)]
        fr = set(ex.loc[ex_n, "comp"])
        frag |= fr
        km_red += ex.loc[ex_n, "km_calc"].sum()
        km_mayor = max([km_mayor] + [ex.loc[ex.comp == f, "km_calc"].sum() for f in fr])
    km_red += km_nuevos

    n1 = [j for j, h in hop.items() if h == 1]
    return hop, dist, {
        "km_sistema": round(sel.km_calc.sum(), 2),
        "km_nuevos": round(km_nuevos, 2),
        "km_existentes_sistema": round(sel.km_calc.sum() - km_nuevos, 2),
        "tramos_nivel1": len(n1),
        "km_nivel1": round(ex.loc[n1, "km_calc"].sum(), 2),
        "fragmentos_unidos": len(frag),
        "piezas_sistema": len(comps_sis),
        "km_red_conectada": round(km_red, 1),
        "km_mayor_previa": round(km_mayor, 1),
    }


def vacio():
    return {k: 0 for k in ["km_sistema", "km_nuevos", "km_existentes_sistema", "tramos_nivel1", "km_nivel1",
                           "fragmentos_unidos", "piezas_sistema", "km_red_conectada", "km_mayor_previa"]}


def calcular_brechas(sis, ex):
    """Extremos sueltos (sin otro tramo a <= tol) con un tramo a <= BRECHA_MAX_M."""
    todo = pd.concat([
        ex[["geometry", "comp"]].assign(capa="existente", nombre=ex.get("EJE_VIA", "")),
        sis[["geometry"]].assign(comp=-1, capa="sistema", nombre=sis[CAMPO_NOMBRE].fillna(
            sis[CAMPO_SISTEMA].astype(str) + " (" + sis[CAMPO_TIPO].astype(str) + ")")),
    ], ignore_index=True)
    todo = gpd.GeoDataFrame(todo, geometry="geometry", crs=ex.crs)
    zona = sis.geometry.union_all().buffer(RADIO_BRECHAS_M)
    sidx = todo.sindex
    filas, vistos = [], set()
    for i, geom in enumerate(todo.geometry):
        for linea in getattr(geom, "geoms", [geom]):
            for xy in (linea.coords[0], linea.coords[-1]):
                p = Point(xy)
                if not zona.contains(p):
                    continue
                cand = [j for j in sidx.query(p, predicate="dwithin", distance=BRECHA_MAX_M) if j != i]
                if not cand:
                    continue
                dists = [(todo.geometry.iloc[j].distance(p), j) for j in cand]
                if min(dists)[0] <= TOLERANCIA_M:
                    continue  # extremo conectado
                d, j = min(dists)
                par = tuple(sorted((i, j)))
                if par in vistos:
                    continue
                vistos.add(par)
                ci, cj = todo.comp.iloc[i], todo.comp.iloc[j]
                filas.append({
                    "largo_m": round(d),
                    "desde": f"{todo.capa.iloc[i]}: {todo.nombre.iloc[i]}",
                    "hacia": f"{todo.capa.iloc[j]}: {todo.nombre.iloc[j]}",
                    "une_fragmentos": bool(ci != cj or ci == -1),
                    "geometry": shortest_line(p, todo.geometry.iloc[j]),
                })
    return gpd.GeoDataFrame(filas, geometry="geometry", crs=ex.crs) if filas else \
        gpd.GeoDataFrame(columns=["largo_m", "geometry"], geometry="geometry", crs=ex.crs)


def a_geojson(gdf, decimales=6, simplificar=1.0):
    g = gdf.copy()
    g["geometry"] = g.geometry.simplify(simplificar)
    g = g.to_crs("EPSG:4326")
    fc = json.loads(g.to_json(na="null", drop_id=True))

    def redondear(c):
        return [round(c[0], decimales), round(c[1], decimales)] if isinstance(c[0], float) else [redondear(x) for x in c]

    for f in fc["features"]:
        if f["geometry"]:
            f["geometry"]["coordinates"] = redondear(f["geometry"]["coordinates"])
        for k, v in list(f["properties"].items()):
            if isinstance(v, float) and v.is_integer() and k.startswith("h_"):
                f["properties"][k] = int(v)
    return fc


if __name__ == "__main__":
    main()
