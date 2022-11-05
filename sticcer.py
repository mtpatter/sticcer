#!/usr/bin/env python

"""
STICCER: Sustainable Tech Insights and Cloud Carbon Efficiency Report

Start prometheus and friends to monitor containers with label sticcer=GROUP_NAME.
Use my dockprom fork for Docker for Mac.
$ cd PATH_TO_GITHUB_REPO/dockprom
$ docker-compose up

Build image:
$ docker build -t dash -f Dockerfile.dash .

Run this dashboard on port 8050 (locally with Docker for Mac):
$ docker run -it --rm --add-host=host.docker.internal:host-gateway \
    -p 8050:8050 -v $PWD:/dash \
    --label sticcer=dashgroup \
    dash python sticcer.py -f sticcer-config.json
"""
import argparse
import json
import requests
import pytz
import plotly.graph_objects as go
from collections import deque
from datetime import datetime, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output


# prometheus helpers
def get_prom_metric(prometheus_uri, query):
    response = requests.get(prometheus_uri + '/api/v1/query',
                            params={'query': query},
                            auth=("admin", "admin"))

    results = response.json()['data']['result']
    try:
        metric_value = results[0]['value'][1]
    except IndexError:
        metric_value = 0
    return metric_value


# carb aware helpers
def get_loc_current_carb(carb_aware_uri, location):
    if type(location) == str:
        emissions_current_query = {"location": [location]}
        resp = requests.get(carb_aware_uri + "/emissions/bylocations?",
                            params=emissions_current_query)
        carbon_intensity = resp.json()[0]["rating"]
        return carbon_intensity

    elif type(location) == list:
        emissions_current_query = {"location": location}
        resp = requests.get(carb_aware_uri + "/emissions/bylocations?",
                            params=emissions_current_query)
        carbon_intensities = {resp.json()[x]["location"]: resp.json()[x]["rating"] for x in range(len(location))}
        return carbon_intensities


def main(args):
    with open(args.config, "r") as f:
        json_config = json.load(f)

    carb_aware_uri = json_config["carb_aware_uri"]
    prometheus_uri = json_config["prometheus_uri"]
    container_groups = json_config["container_group_list"]
    location_list = json_config["location_list"]
    current_location = json_config["location"]
    convert_g_per_hour = 0.000035  # prometheus cpus x carb intensity x this constant

    # stylesheet with the .dbc class
    dbc_css = "https://cdn.jsdelivr.net/gh/AnnMarieW/dash-bootstrap-templates/dbc.min.css"
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY, dbc_css])

    header = html.H2([
                      "STICCER", html.Br(),
                      "Sustainable Tech Insights and Cloud Carbon Efficiency Report"],
                     className="bg-success text-white p-2 mb-2 text-center"
                     )

    # Daily Insights
    score_card = dbc.Card(
        id="score_card")

    total_numbers = dbc.Card(
        id="total_numbers_card")

    opps_card = dbc.Card(html.Div(
        [
            html.H4("Top Opportunities", className="bg-light text-black p-2 mb-2 text-center"),
            html.P("Shift services to optimal regions.", className="text-left p-2"),
            dash_table.DataTable(
                id="table",
                columns=[{"name": i, "id": i} for i in ["Service", "Region", "Time"]],
                data=[{"Service": container_groups[0], "Region": "westus", "Time": "[2pm local]"},
                      {"Service": container_groups[1], "Region": "westus", "Time": "[2pm local]"}],
                style_table={"overflowX": "auto"},
                style_data={"textAlign": "left"},
                style_header={"backgroundColor": "rgb(50, 50, 50)", "color": "white",
                              "textAlign": "left"}
                ),
        ],
        id="emitters_card",
        # className="mb-5",
        ))

    # Real-time viz section
    dropdown_containers = html.Div(
        [
            html.P([dbc.Label("Select sticcer label group.")], className="p-2"),
            dcc.Dropdown(
                ["all"] + container_groups,
                "all",
                id="container_group",
                clearable=False,
            ),
        ],
        className="p2",
    )

    metrics = ["Average location", "Optimal location"]
    checklist = html.Div(
        [
            dbc.Label("Select comparisons."),
            dbc.Checklist(
                id="metrics_checklist",
                options=[{"label": i, "value": i} for i in metrics],
                value=metrics,
                inline=True,
            ),
        ],
        className="p-2",
    )

    controls_con = dbc.Col(
        [dropdown_containers,
         ],
        # body=True,
    )
    controls_check = dbc.Col(
        [checklist,
         ],
        # body=True,
    )

    # Forecast section
    dropdown_region = html.Div(
        [
            dbc.Label("Select reference region."),
            dcc.Dropdown(
                location_list,
                current_location,
                id="region_group",
                clearable=False,
            ),
        ],
        className="mb-4 text-left p-2",
    )

    app.layout = dbc.Container(
        [header,
         dbc.Row(  # row
            [dbc.Col(  # column
                    [
                     score_card,
                     html.Br(),
                     total_numbers,
                     html.Br(),
                     opps_card,
                     ],
             width=4,
             ),  # end column

             dbc.Col(  # column 3
                   [
                    dbc.Card([
                        html.H3("Real-time CO2 Emissions",
                                className="bg-primary text-white p-2 mb-2 text-center"),
                        dbc.Row([
                            controls_con,
                            controls_check]),
                        dcc.Graph(id='cpu_usage_secs_per_minute',
                                  # animate=True
                                  ),
                        dcc.Interval(id="refresh_interval",
                                     interval=1*10000,  # in milliseconds
                                     n_intervals=0
                                     ),
                     ]),  # end card
                    ],  # end column
             width=8,),
             ]  # end column
            ),  # end row 1

         html.Br(),

         dbc.Row(  # row 2
            [
             dbc.Col([
                     html.H3("Regional Emissions 24-hr Forecasts",
                             className="bg-primary text-white p-2 mb-2 text-center"),
                     dbc.Card([
                                dbc.Col(  # column 1
                                    [dropdown_region,
                                     ],
                                    width=4,
                                ),  # end column
                                dbc.Col([
                                         dcc.Graph(id='cpu_usage_forecast',
                                                   animate=False),
                                        ],
                                        width=12),
                                ]),  # end card
                     ], width=12)  # end column outer
             ]),  # end row 2

         html.Br(),
         ]  # end list in container
        )  # end container

    cpu_data = {'x': deque(maxlen=60),
                'current': deque(maxlen=60),
                'average': deque(maxlen=60),
                'optimal': deque(maxlen=60)}

# CALLBACKS

    @app.callback(Output('score_card', 'children'),
                  [Input('refresh_interval', 'n_intervals')],)
    def update_score(n_intervals):
        # query = 'sum(sum_over_time(container_cpu_usage_seconds_total[1d]))'
        # prom = get_prom_metric(prometheus_uri, query)  # TODO - convert and construct score
        val = html.Div(
            [
                html.H3("Daily Insights", className="bg-primary text-white p-2 mb-2 text-center"),
                html.H4("Carbon Efficiency Score", className="bg-light text-black p-2 mb-2 text-center"),
                html.H2("85", className="text-success text-center"),
                html.P("Previous day: 65", className="text-left p-2 mb-2"),
                html.P("7-day average: 75", className="text-left p-2"),
            ],
            )
        return val

    @app.callback(Output('total_numbers_card', 'children'),
                  [Input('refresh_interval', 'n_intervals')],)
    def update_total_numbers(n_intervals):
        query = 'sum(sum_over_time(container_cpu_usage_seconds_total[1d]))'
        prom = get_prom_metric(prometheus_uri, query)
        current_carb = get_loc_current_carb(carb_aware_uri, current_location)
        # prom = cpusecs/day x convert_g_per_hour |  */ 0.000277778
        emissions = float(prom) * float(current_carb) * 2.10 / 6000 / 86400  # TODO: should be actual location not current

        val = html.Div(
            [
                html.H4("Today's CO2 Total", className="bg-light text-black p-2 mb-2 text-center"),
                html.P(str(round(emissions)) + ' grams', className="text-center"),
                html.P("[insert equivalent carbon credit]", className="text-center"),
            ],
            # className="mb-5",
            ),
        return val

    @app.callback(Output('cpu_usage_secs_per_minute', 'figure'),
                  [Input('refresh_interval', 'n_intervals'),
                   Input('container_group', 'value'),
                   Input('metrics_checklist', 'value'),
                   ])
    def update_realtime(n_intervals, c_group, metrics):
        x = datetime.now(tz=pytz.timezone(json_config["pytz_timezone"])).strftime('%Y-%m-%d %H:%M:%S.%f')
        # prometheus: CPU seconds per clock minute
        if c_group == 'all':
            query = 'sum(rate(container_cpu_usage_seconds_total[1m]))'
        else:
            query = 'sum(rate(container_cpu_usage_seconds_total{container_label_sticcer="' + c_group + '"}[1m]))'
        prom = get_prom_metric(prometheus_uri, query)

        # carb aware: carbon intensity in gCO2/kWh
        carbs_dict = get_loc_current_carb(carb_aware_uri, location_list)
        current_carb = get_loc_current_carb(carb_aware_uri, current_location)
        average_carb = sum(carbs_dict.values())/len(carbs_dict)
        optimal_carb = min(carbs_dict.values())  # TODO get optimal location for legend label

        call_data = cpu_data
        call_data['current'].append(float(current_carb)*float(prom)*convert_g_per_hour)
        call_data['average'].append(float(average_carb)*float(prom)*convert_g_per_hour)
        call_data['optimal'].append(float(optimal_carb)*float(prom)*convert_g_per_hour)
        call_data['x'].append(x)
        data = [go.Scatter(
                    x=list(call_data['x']),
                    y=list(call_data['current']),
                    name=c_group+": " + current_location,
                    mode="lines"
                    )]
        if "Optimal location" in metrics:
            data.append(
                go.Scatter(
                    x=list(call_data['x']),
                    y=list(call_data['optimal']),
                    name="Optimal location",
                    mode="lines"
                    )
                )
        if "Average location" in metrics:
            data.append(
                go.Scatter(
                    x=list(call_data['x']),
                    y=list(call_data['average']),
                    name="Average location",
                    mode="lines"
                    ),)
        fig = {'data': data,
               'layout': {
                        'title': 'Rate of CO2 emissions',
                        'yaxis': {
                            'title': 'Emission rate (grams/hour)'}
                        }
               }
        return fig

    @app.callback(Output('cpu_usage_forecast', 'figure'),
                  [Input('region_group', 'value'),
                   ])
    def update_forecast(region_group):
        x_hours = [(datetime.now(tz=pytz.timezone(json_config["pytz_timezone"]))+timedelta(hours=0.5*n)).strftime('%Y-%m-%d %H:%M:%S.%f') for n in [x for x in range(0, 49)]]
        # prometheus: CPU seconds per clock minute
        n_hours = [x for x in range(1, 49)]
        queries = ['sum(predict_linear(container_cpu_usage_seconds_total{container_label_sticcer="dashgroup"}[1m],' + str(n) + '*1800))'
                   for n in n_hours]
        proms = [float(get_prom_metric(prometheus_uri, q)) for q in queries]

        # carb aware: carbon intensity in gCO2/kWh
        carb = get_loc_current_carb(carb_aware_uri, region_group)  # TODO change to actual forecast time
        vals = [float(prom) * float(carb) * convert_g_per_hour for prom in proms]
        #rate_vals = [val/n_hour for val, n_hour in zip(vals, n_hours)]
        fig = {'data': [{'x': x_hours,
                         'y': vals}],
                         #'y': [proms[i]/n_hour[i]/2 for i in range(len(proms))]}],
               'layout': {
                        'title': 'Regional forecasted CO2 emissions',
                        'yaxis': {
                            'title': 'Expected Emission Levels (grams)'}
                        }
               }
        return fig

    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-f",
        "--config",
        help="config file",
        required=True)
    args = parser.parse_args()

    app = main(args)

    app.run_server(port=8050, host='0.0.0.0', debug=True)
