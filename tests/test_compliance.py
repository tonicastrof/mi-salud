from _lib.compliance import compare, flatten, align, evaluate_step

HR_ZONES = [{"min": 0, "max": 120}, {"min": 120, "max": 145}, {"min": 145, "max": 160},
            {"min": 160, "max": 172}, {"min": 172, "max": -1}]

WARM = {"type": "warmup", "label": "Calentamiento", "duration": "15 min", "target": "FC zona 2",
        "end": {"type": "time", "value": 900}, "goal": {"type": "hr_zone", "zone": 2}}
SERIE = {"type": "interval", "label": "Serie", "duration": "1 km", "target": "4:15–4:30 /km",
         "end": {"type": "distance", "value": 1000}, "goal": {"type": "pace", "fast": 255, "slow": 270}}
REC = {"type": "recovery", "label": "Recuperación", "duration": "2:00", "target": "FC zona 2",
       "end": {"type": "time", "value": 120}, "goal": {"type": "hr_zone", "zone": 2}}
COOL = {"type": "cooldown", "label": "Vuelta a la calma", "duration": "10 min", "target": None,
        "end": {"type": "time", "value": 600}, "goal": None}

WORKOUT = {"date": "2026-10-05", "title": "Umbral 4x1000", "duration_sec": 3000,
           "steps": [WARM, {"repeat": 4, "steps": [SERIE, REC]}, COOL]}


def lap(sec, m, hr=140):
    return {"elapsed": sec, "moving": sec, "distance": m, "hr": hr, "watts": 0}


def laps(serie_secs, rec_hr=135, cool_sec=600):
    out = [lap(900, 2600, 138)]
    for s in serie_secs:
        out += [lap(s, 1000, 168), lap(120, 300, rec_hr)]
    return out + [lap(cool_sec, 1500, 130), lap(8, 10, 120)]   # la última: parar el reloj


def test_flatten_y_align():
    flat = flatten(WORKOUT["steps"])
    assert len(flat) == 10 and flat[1]["rep"] == 1 and flat[1]["reps"] == 4
    assert align(flat, laps([260] * 4)) is not None      # la vuelta residual se descarta
    assert align(flat, laps([260] * 3)) is None


def test_clavado():
    c = compare(WORKOUT, {"name": "Umbral"}, laps([262, 260, 258, 261]), HR_ZONES)
    assert c["aligned"] and c["score"] >= 85 and c["verdict"].startswith("Clavado")
    assert any("Series en su ritmo" in n for n in c["notes"])


def test_series_rapidas_y_recuperaciones_a_tope():
    c = compare(WORKOUT, {"name": "Umbral"}, laps([235, 236, 238, 237], rec_hr=158), HR_ZONES)
    assert c["score"] < 50
    texto = " ".join(c["notes"])
    assert "Las series fueron rápidas" in texto
    assert "Lo suave no fue suave: recuperaciones a 158 ppm" in texto
    assert "✗ Serie 1/4" in c["summary"]


def test_perder_ritmo_y_recortar():
    c = compare(WORKOUT, {"name": "Umbral"}, laps([256, 262, 268, 280], cool_sec=200), HR_ZONES)
    texto = " ".join(c["notes"])
    assert "Fuiste perdiendo ritmo" in texto
    assert "Recortaste vuelta a la calma" in texto


def test_rodaje_base_fuera_de_zona():
    base = {"date": "2026-10-05", "title": "Base", "steps": [
        {"type": "interval", "label": "Carrera", "duration": "45 min", "target": "FC zona 2",
         "end": {"type": "time", "value": 2700}, "goal": {"type": "hr_zone", "zone": 2}}]}
    c = compare(base, {"name": "Rodaje"}, [lap(2700, 8200, 158)], HR_ZONES)
    assert c["score"] == 33   # duración bien (pesa 1), FC muy por encima (pesa 2)
    assert any("Te saliste de la zona por arriba" in n for n in c["notes"])
    ok = compare(base, {"name": "Rodaje"}, [lap(2700, 7600, 138)], HR_ZONES)
    assert ok["score"] == 100 and any("bien controlado" in n for n in ok["notes"])


def test_sin_emparejar_compara_totales():
    c = compare(WORKOUT, {"name": "X"}, [lap(1500, 5000), lap(1400, 4800)], HR_ZONES)
    assert not c["aligned"] and c["steps"] == []
    assert "No pude emparejar" in c["notes"][0]
    assert c["score"] is not None


def test_paso_con_fc_por_ppm():
    st = {"type": "interval", "label": "Tempo", "end": None,
          "goal": {"type": "hr", "lo": 150, "hi": 160}}
    assert evaluate_step(st, lap(600, 2000, 155))["status"] == "ok"
    assert evaluate_step(st, lap(600, 2000, 163))["status"] == "warn"
    assert evaluate_step(st, lap(600, 2000, 175))["status"] == "bad"


# ─── Con vuelta automática cada km: se corta la grabación por el plan ───

def grabacion(tramos, hr=140):
    """tramos: [(segundos, velocidad m/s, fc)] → streams de Strava a 1 Hz."""
    t, d, v, h, mv = [0], [0.0], [0.0], [hr], [True]
    for secs, vel, fc in tramos:
        for _ in range(int(secs)):
            t.append(t[-1] + 1)
            d.append(d[-1] + vel)
            v.append(vel)
            h.append(fc)
            mv.append(True)
    return {"time": t, "distance": d, "velocity_smooth": v, "heartrate": h, "moving": mv}


def km_laps(streams):
    """Vueltas automáticas cada km, como las graba el reloj."""
    out, last_t, last_d = [], 0, 0
    for tt, dd in zip(streams["time"], streams["distance"]):
        if dd - last_d >= 1000:
            out.append(lap(tt - last_t, dd - last_d))
            last_t, last_d = tt, dd
    out.append(lap(streams["time"][-1] - last_t, streams["distance"][-1] - last_d))
    return out


BASE_COACH = {"date": "2026-10-05", "title": "Base", "duration_sec": 1800, "steps": [
    {"type": "interval", "label": "Serie", "duration": "30 min", "target": "4:29–5:08 /km",
     "end": {"type": "time", "value": 1800}, "goal": {"type": "pace", "fast": 269, "slow": 308}}]}


def test_base_de_garmin_coach_con_vueltas_por_km():
    st = grabacion([(1805, 1000 / 290, 142)])          # 30 min a 4:50/km
    laps_ = km_laps(st)
    assert len(laps_) == 7                              # 6 km enteros + resto
    c = compare(BASE_COACH, {"name": "Rodaje"}, laps_, HR_ZONES, st)
    assert c["method"] == "streams" and c["score"] == 100
    assert c["steps"][0]["label"] == "Carrera"
    assert "100% en rango" in c["steps"][0]["done"]
    assert any("Ritmo medio 4:50/km, dentro del objetivo" in n for n in c["notes"])
    assert any("Muy regular" in n for n in c["notes"])


def test_base_demasiado_rapido_y_a_tirones():
    st = grabacion([(600, 1000 / 240, 160), (600, 1000 / 330, 140), (600, 1000 / 240, 160)])
    c = compare(BASE_COACH, {"name": "Rodaje"}, km_laps(st), HR_ZONES, st)
    assert c["steps"][0]["status"] != "ok"
    texto = " ".join(c["notes"])
    assert "% del tiempo dentro del rango" in texto


def test_series_cortando_la_grabacion():
    st = grabacion([(900, 2.9, 138)] +
                   [(240, 1000 / 236, 170), (120, 2.6, 150)] * 4 +
                   [(400, 2.8, 130)])
    serie = dict(SERIE, end={"type": "time", "value": 240})
    w = {"date": "2026-10-05", "title": "Umbral", "steps": [WARM, {"repeat": 4, "steps": [serie, REC]},
                                                              dict(COOL, end=None)]}
    laps_ = km_laps(st)
    assert len(laps_) == 10            # tantas vueltas como pasos, por casualidad
    c = compare(w, {"name": "X"}, laps_, HR_ZONES, st)
    assert c["method"] == "streams" and len(c["steps"]) == 10
    assert "Las series fueron rápidas" in " ".join(c["notes"])
    assert c["steps"][-1]["done"].startswith("6:4")    # la vuelta a la calma se queda el resto


def test_se_acabo_antes_de_tiempo():
    st = grabacion([(1200, 1000 / 290, 142)])          # 20 de 30 min
    c = compare(BASE_COACH, {"name": "Rodaje"}, km_laps(st), HR_ZONES, st)
    assert "duración corto" in c["steps"][0]["issues"]
    assert any("Recortaste" in n for n in c["notes"])
