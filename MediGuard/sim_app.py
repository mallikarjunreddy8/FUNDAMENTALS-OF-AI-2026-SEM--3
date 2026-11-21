"""
MediGuard - interactive simulation dashboard (Mesa + Solara).

Run:   solara run sim_app.py        then open http://localhost:8765
       (Windows: run.bat -> option 2)

The town: 🏥 licensed pharmacy (green), 🏚 unlicensed shop (orange), closed shop (grey),
👤 patients (blue = has the MediGuard app, light = no app), 🕵 drug inspector (purple).
Press ▶ to run, change the sliders and press Reset to compare.
"""

import solara
from mesa.visualization import SolaraViz, make_plot_component, make_space_component

from mediguard.agents import Inspector, Patient, Pharmacy
from mediguard.model import DEFAULT_SCENARIO, SCENARIOS, MediGuardModel


def portrayal(agent):
    if isinstance(agent, Pharmacy):
        color = "#9ca3af" if not agent.is_open else ("#15803d" if agent.licensed else "#ea580c")
        return {"color": color, "marker": "s", "size": 140, "zorder": 2}
    if isinstance(agent, Inspector):
        return {"color": "#7c3aed", "marker": "D", "size": 90, "zorder": 3}
    if isinstance(agent, Patient):
        return {"color": "#1d4ed8" if agent.has_app else "#93c5fd", "marker": "o", "size": 14, "zorder": 1}
    return {"color": "#000000", "size": 1}


def summary(model):
    s = model.summary()
    mix = ", ".join(f"{k} {model.mix(k):.0f}%" for k in ("crude", "copied_qr", "perfect"))
    return solara.Markdown(f"""
**Day {model.steps}** · scenario *{model.scenario}*

| | |
|---|---|
| Bad medicine sold | **{s['S&F sold (%)']:.2f}%** |
| Bad medicine actually taken | **{s['S&F taken (%)']:.2f}%** |
| Bad packs caught by the app | {s['Caught by app (%)'] if s['Caught by app (%)'] is not None else '-'} % |
| Genuine packs wrongly flagged | {s['False alarms (%)'] if s['False alarms (%)'] is not None else '-'} % |
| Harm per 1000 doses | {s['Harm per 1000 doses']} |
| Shops closed / batches on alert | {model.closures} / {len(model.detector.alerts)} |
| Counterfeiters' production | {mix} |

Each app scan runs the real detection agent on a pack built from the
253,973-medicine dataset.
""")


model_params = {
    "scenario": {"type": "Select", "value": DEFAULT_SCENARIO, "values": list(SCENARIOS), "label": "Research scenario"},
    "app_adoption": {"type": "SliderFloat", "value": 0.3, "min": 0, "max": 1, "step": 0.05, "label": "People using the app"},
    "confirm_prob": {"type": "SliderFloat", "value": 0.7, "min": 0, "max": 1, "step": 0.1,
                     "label": "App users who confirm the details"},
    "ocr_error": {"type": "SliderFloat", "value": 0.02, "min": 0, "max": 0.1, "step": 0.01, "label": "Camera misreads (share of characters)"},
    "report_prob": {"type": "SliderFloat", "value": 0.5, "min": 0, "max": 1, "step": 0.1, "label": "Chance a flagged pack is reported"},
    "n_inspectors": {"type": "SliderInt", "value": 1, "min": 0, "max": 4, "step": 1, "label": "Drug inspectors"},
    "intelligence_led": {"type": "Checkbox", "value": True, "label": "Inspectors visit reported shops first"},
    "adaptive": {"type": "Checkbox", "value": True, "label": "Counterfeiters adapt (arms race)"},
    "n_counterfeiters": {"type": "SliderInt", "value": 2, "min": 0, "max": 5, "step": 1, "label": "Counterfeiters"},
    "unlicensed_share": {"type": "SliderFloat", "value": 0.25, "min": 0, "max": 0.6, "step": 0.05, "label": "Unlicensed shops"},
    "qr_share": {"type": "SliderFloat", "value": 0.5, "min": 0, "max": 1, "step": 0.1, "label": "Products with a QR code"},
    "n_patients": {"type": "SliderInt", "value": 200, "min": 50, "max": 500, "step": 50, "label": "Patients"},
    "n_pharmacies": {"type": "SliderInt", "value": 12, "min": 4, "max": 30, "step": 1, "label": "Pharmacies"},
    "seed": {"type": "InputText", "value": 42, "label": "Random seed"},
}

model = MediGuardModel(seed=42)

page = SolaraViz(
    model,
    components=[
        make_space_component(portrayal),
        summary,
        make_plot_component({"S&F sold (%)": "#ea580c", "S&F taken (%)": "#b42318"}),
        make_plot_component({"Caught by app (%)": "#0f766e", "False alarms (%)": "#9ca3af"}),
        make_plot_component({"Crude fakes (%)": "#2f5f9e", "Copied-QR fakes (%)": "#c2410c", "Perfect clones (%)": "#7c3aed"}),
        make_plot_component({"Harm events": "#b42318", "Reports": "#0f766e", "Shops closed": "#4b5563"}),
    ],
    model_params=model_params,
    name="MediGuard - fake medicine in a town",
    play_interval=150,
)
page  # noqa: B018 - Solara shows this
