# mood_sync_dashboard_with_stk_ai_secretary.py
import os
import json
import time
import hashlib
import dash
import base64
import re
import requests
from dash import html, dcc, Input, Output, State
from dash import no_update, Output, Input, State, html
import smtplib
from email.message import EmailMessage
import dash_bootstrap_components as dbc
from datetime import datetime
import random
import pandas as pd
import numpy as np
from dash import Dash, dcc, html, Input, Output, State
import plotly.graph_objects as go
import plotly.express as px
app = Dash(__name__, suppress_callback_exceptions=True)  # <-- add suppress here


# ----------------------------
# Setup & constants
# ----------------------------
np.random.seed(42)

counties = [
    "Nairobi","Mombasa","Kisumu","Nakuru","Eldoret","Thika","Malindi","Meru","Machakos","Kakamega",
    "Nyeri","Murang'a","Embu","Kericho","Bomet","Narok","Baringo","Laikipia","Bungoma",
    "Busia","Siaya","Homa Bay","Migori","Kisii","Nyamira","Garissa","Wajir","Mandera","Marsabit",
    "Isiolo","Kitui","Makueni","Taita Taveta","Kilifi","Kwale","Tana River","Samburu","Turkana",
    "West Pokot","Elgeyo Marakwet","Trans Nzoia","Nandi","Vihiga","Tharaka Nithi","Lamu","Kajiado","Kiambu","Kirinyaga"
]

payment_types = ['Mpesa','Airtel Money','Bank Transfer']
sectors = ['Transport','Communication','Retail','Banking','Government','Utilities','Agriculture']

app = Dash(__name__)
app.title = "backspace-2 "

alert_log = []

USERS_FILE = "users.json"

# ----------------------------
# Safaricom Sandbox credentials
# ----------------------------
MPESA_BASE_URL = "https://sandbox.safaricom.co.ke"
CONSUMER_KEY = "bwrYETJX1vaWbOXFTrf7A55oTgfC9YQNq1zoe6bScn6pnkmI"
CONSUMER_SECRET = "y1Njn0Aiq18khzQ5eGJneSG1Ju5dXICMv6ZXGatzEiymyhcGFfdCy1B0ode3MYCS"
SHORTCODE = "174379"  # sandbox test shortcode
PASSKEY = "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919"
CALLBACK_URL = "https://backspace-5pqn.onrender.com"

# ----------------------------
# Helpers: users file read/write
# ----------------------------
def load_users():
    if not os.path.exists(USERS_FILE):
        return []
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def save_users(users):
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)

def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def email_exists(email):
    users = load_users()
    for u in users:
        if u.get("email", "").lower() == (email or "").lower():
            return True
    return False

def add_user(full_name, email, password, subscription, phone, trial_days):
    """
    Save a user to storage including phone and trial days.
    Dict-based storage: users[email] = { ... }
    """
    users = load_users()  # should return {} if file empty

    timestamp = datetime.utcnow().isoformat() + "Z"

    users[email] = {
        "full_name": full_name,
        "email": email,
        "password_hash": hash_password(password),
        "subscription": subscription,
        "phone": phone,
        "trial_days": trial_days,
        "registered_at": timestamp
    }

    save_users(users)
    return True

# ----------------------------
# M-Pesa STK Push (Sandbox)
# ----------------------------
def get_mpesa_oauth_token():
    """
    Retrieves OAuth token from the sandbox.
    """
    url = "https://sandbox.safaricom.co.ke/oauth/v1/generate?grant_type=client_credentials"
    auth_str = f"{CONSUMER_KEY}:{CONSUMER_SECRET}"
    b64 = base64.b64encode(auth_str.encode()).decode()
    headers = {"Authorization": f"Basic {b64}"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("access_token")
    except Exception as e:
        print(f"MPESA OAuth token error: {e}")
        return None

def lipa_na_mpesa_stk_push(phone_number, amount, account_reference="Donation", transaction_desc="Donation"):
    """
    Initiates STK push via Safaricom sandbox.
    phone_number should be in format 07xxxxxxxx or 01xxxxxxxx (no +).
    amount is integer (KES).
    Returns dict with the API response or error info.
    """
    token = get_mpesa_oauth_token()
    if not token:
        return {"success": False, "error": "Failed to obtain MPESA OAuth token."}
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password_str = SHORTCODE + PASSKEY + timestamp
    password = base64.b64encode(password_str.encode()).decode()
    url = f"https://sandbox.safaricom.co.ke/mpesa/stkpush/v1/processrequest"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "BusinessShortCode":"174379",
        "Password":password,
        "Timestamp":timestamp,    
        "TransactionType": "CustomerPayBillOnline",
        "Amount": "100",
        "PartyA": "254742834507",
        "PartyB": "174379",    
        "PhoneNumber":"254742834507",
        "CallBackURL": "https://backspace-5pqn.onrender.com/mpesa_callback",
        "AccountReference": "Donation",
        "TransactionDesc":"Donation",
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        resp.raise_for_status()
        return {"success": True, "response": resp.json()}
    except requests.RequestException as e:
        try:
            return {"success": False, "error": e.response.json() if e.response else str(e)}
        except Exception:
            return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ----------------------------
# Styles & App layout
# ----------------------------
CARD_STYLE = {'backgroundColor':'#161b22','borderRadius':'12px','padding':'15px',
              'marginBottom':'10px','boxShadow':'0 0 10px #58a6ff'}
APP_STYLE = {'backgroundColor':'#0d1117','color':'#fff','fontFamily':'Segoe UI, sans-serif','padding':'20px'}

app.layout = html.Div([
    dcc.Store(id='registered-user', data={}, storage_type='session'),
    dcc.Store(id='active-user', data="", storage_type='session'),
html.Div([
    dcc.Link("Home", href="/", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("Register/login", href="/register", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("AI ideas", href="/ai", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("Donate", href="/donation", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("Join us!", href="/partnership", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("AI manager", href="/ai_secretary", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'})
], style={
    'backgroundColor':'#1f6feb',
    'display':'flex',
    'flexWrap':'wrap',          # <-- Allow wrapping on small screens
    'justifyContent':'center',
    'alignItems':'center',
    'gap':'8px',
    'marginBottom':'18px',
    'borderRadius':'6px',
    'padding':'8px'             # <-- Optional: adds some space when wrapped
}),
    dcc.Location(id='url', refresh=False),
    dcc.Location(id='redirect-after-reg', refresh=True),
 # placeholders for dynamically created IDs
    html.Button(id='ai-secretary-btn', style={'display': 'none'}),
    html.Button(id='ai-only-convert', style={'display': 'none'}),
    html.Button(id='ask-btn', style={'display': 'none'}),
    dcc.Interval(id='interval-update', interval=1000, n_intervals=0),
    html.Button(id='partner-send', style={'display': 'none'}),
    html.Button(id='donate-btn', style={'display': 'none'}),
    html.Button(id='register-btn', style={'display': 'none'}),
    html.Div(id='page-content'),
    html.Div(id='login-message', style={"minHeight": "28px", "marginTop": "6px", "textAlign": "center"})
], style=APP_STYLE)
# ----------------------------
# Dashboard layout (responsive & centered)
# ----------------------------
def dashboard_layout():
    return html.Div([
        html.Div([
            html.Label(
                "Select County:", 
                style={
                    'color':'#58a6ff',
                    'fontWeight':'bold',
                    'display':'block',      # ensures label is above dropdown
                    'textAlign':'center',
                    'marginBottom':'8px'
                }
            ),
            dcc.Dropdown(
                id='region-dropdown',
                options=[{'label': c, 'value': c} for c in counties],
                value='Nairobi',
                clearable=False,
                style={
                    'backgroundColor':'green',
                    'color':'red',
                    'border':'1px solid #58a6ff',
                    'borderRadius':'6px',
                    'fontWeight':'bold',
                    'width':'60%',
                    'margin':'0 auto',       # centers dropdown
                    'boxShadow':'0 0 8px #58a6ff',
                    'textAlign':'center'
                }
            )
        ], style={
            'width':'100%',
            'margin':'0 auto',
            'marginBottom':'20px',
            'textAlign':'center'       # ensures the whole block is centered
        }),

        # ---------- Graphs & AI Section (Responsive) ----------
        html.Div(
            children=[
                # Left side: Graphs
                html.Div(
                    children=[
                        dcc.Graph(id='tpm-chart', style={'height':'300px', 'width':'100%'}),
                        dcc.Graph(id='payment-chart', style={'height':'450px', 'width':'100%'}),
                        dcc.Graph(id='sector-chart', style={'height':'400px', 'width':'100%'}),
                        dcc.Graph(id='top-counties-chart', style={'height':'400px', 'width':'100%'}),
                        dcc.Graph(id='top-sectors-chart', style={'height':'450px', 'width':'100%'}),
                        dcc.Graph(id='peak-hour-heatmap', style={'height':'300px', 'width':'100%'}),
                    ],
                    style={
                        'flex':'2 1 600px',   # Flexible width
                        'minWidth':'300px',
                        'paddingRight':'20px'
                    }
                ),

                # Right side: AI Assistant & Alerts (unchanged)
                html.Div(
                    children=[
                        html.H3("💬 AI Assistant", style={'color':'#58a6ff','borderRadius':'10px'}),
                        dcc.Textarea(
                            id='user-question',
                            placeholder='Ask about averages transactions, totals transactions, or current transactions per minute...',
                            style={
                                'width':'100%',
                                'height':100,
                                'backgroundColor':'#0d1117',
                                'color':'white',
                                'marginBottom':'10px',
                                'borderRadius':'10px'
                            }
                        ),
                        html.Button(
                            "Ask",
                            id='ask-btn',
                            n_clicks=0,
                            style={
                                'width':'100%',
                                'padding':'10px',
                                'backgroundColor':'#1f6feb',
                                'color':'white',
                                'border':'none',
                                'borderRadius':'8px'
                            }
                        ),
                        html.Div(id='ai-answer', style={**CARD_STYLE,'backgroundColor':'#21262d','marginTop':'10px'}),
                        html.H3("⚠️ Recent Alerts", style={'color':'#d9534f','marginTop':'20px'}),
                        html.Div(
                            id='alert-log',
                            style={
                                'backgroundColor':'#21262d',
                                'color':'#ffffff',
                                'height':'200px',
                                'overflowY':'scroll',
                                'padding':'10px',
                                'borderRadius':'10px',
                                'boxShadow':'0 0 10px #ff6f58'
                            }
                        )
                    ],
                    style={
                        'flex':'1 1 300px',
                        'minWidth':'250px'
                    }
                )
            ],
            style={
                'display': 'flex',
                'flexDirection': 'row',
                'flexWrap': 'wrap',       # Stack on mobile
                'gap': '20px',
                'width': '100%',
                'maxWidth': '1200px',
                'margin': 'auto'
            }
        ),

        # ---------- Update Interval ----------
        dcc.Interval(id='interval-update', interval=5000, n_intervals=0)
    ])
# ----------------------------
# Registration + Login layout (centered links stacked, inputs/buttons centered)
# ----------------------------
def registration_layout():
    return html.Div([
        # Dark overlay
        html.Div(
            id="registration-modal-background",
            style={
                "position": "fixed",
                "top": 0, "left": 0,
                "width": "100%", "height": "100%",
                "backgroundColor": "rgba(0,0,0,0.6)",
                "display": "flex", "justifyContent": "center", "alignItems": "center",
                "zIndex": 999, "overflow": "auto", "backdropFilter": "blur(3px)"
            },
            children=[
                # Card
                html.Div(
                    id="registration-modal",
                    style={
                        "backgroundColor": "#0d1117",
                        "borderRadius": "14px",
                        "padding": "28px",
                        "width": "92%",
                        "maxWidth": "480px",
                        "maxHeight": "88vh",
                        "overflowY": "auto",
                        "boxShadow": "0 8px 30px rgba(0,0,0,0.6)",
                        "color": "white",
                        "display": "flex",
                        "flexDirection": "column",
                        "alignItems": "center",
                        "gap": "14px",
                        "textAlign": "center"
                    },
                    children=[

                        html.H2("Hi there", style={'color': '#f0f8ff', 'margin': '4px 0 6px 0'}),

                        # === STACKED LINKS (centered, one above the other) ===
                        html.Div(
                            style={
                                "width": "100%",
                                "display": "flex",
                                "flexDirection": "column",
                                "alignItems": "center",
                                "gap": "8px",
                                "marginBottom": "6px"
                            },
                            children=[
                                html.Button(
                                    "Register",
                                    id="link-register",
                                    n_clicks=0,
                                    style={
                                        "width": "60%", "maxWidth": "260px",
                                        "padding": "8px 12px",
                                        "borderRadius": "999px",
                                        "border": "1px solid rgba(88,166,255,0.15)",
                                        "background": "linear-gradient(90deg,#1a73e8, #1558c9)",
                                        "color": "white",
                                        "fontWeight": "600",
                                        "cursor": "pointer"
                                    }
                                ),
                                html.Button(
                                    "Login",
                                    id="link-login",
                                    n_clicks=0,
                                    style={
                                        "width": "60%", "maxWidth": "260px",
                                        "padding": "8px 12px",
                                        "borderRadius": "999px",
                                        "border": "1px solid rgba(255,255,255,0.06)",
                                        "background": "transparent",
                                        "color": "#cfe8ff",
                                        "fontWeight": "600",
                                        "cursor": "pointer"
                                    }
                                )
                            ]
                        ),

                        # Keep the Tabs component (so older callbacks that read register-login-tabs keep working)
                        dbc.Tabs(
                            [
                                dbc.Tab(label="Register", tab_id="tab-register"),
                                dbc.Tab(label="Login", tab_id="tab-login"),
                            ],
                            id="register-login-tabs",
                            active_tab="tab-register",
                            className="mb-2",
                            style={"width": "100%", "display": "none"}  # hide the visible default tab row (we use stacked links)
                        ),

                        # Centered form container (controls are full-width inside this)
                        html.Div(
                            id="register-login-content",
                            style={
                                "width": "100%",
                                "maxWidth": "360px",   # center column width
                                "display": "flex",
                                "flexDirection": "column",
                                "alignItems": "stretch"
                            }
                        ),

                        # Close button full width inside the card
                        html.A(
                            "Close",
                            href="/",
                            style={
                                "display": "block",
                                "width": "100%",
                                "maxWidth": "360px",
                                "padding": "12px",
                                "borderRadius": "10px",
                                "background": "#d9534f",
                                "color": "white",
                                "fontWeight": "700",
                                "textDecoration": "none",
                                "textAlign": "center",
                                "marginTop": "8px"
                            }
                        ),

                        # Message area
                        html.Div(id="register-message", style={"minHeight": "28px", "textAlign": "center"}),
                        html.Div(id='login-message', style={"minHeight": "28px", "marginTop": "6px", "textAlign": "center"})
                    ]
                )
            ]
        ),

        # Hidden login section (unchanged)
        html.Div(
            id='login-section',
            style={'marginTop': '1000px'},
            children=[
                html.H2("Login Section"),
                dcc.Input(
                    id='login-email', type='email', placeholder='Email',
                    style={'width':'100%','padding':'10px','marginBottom':'10px','marginRight':'5px'}
                ),
                dcc.Input(
                    id='login-password', type='password', placeholder='Password',
                    style={'width':'100%','padding':'10px','marginBottom':'10px'}
                ),
                html.Button(
                    'Submit Login', id='login-btn', n_clicks=0,
                    style={'width':'100%','padding':'12px','background':'#1f6feb','color':'white','fontWeight':'600','borderRadius':'10px'}
                ),
                html.Div(
                    id='login-message',
                    style={'minHeight': '28px','marginTop':'6px','textAlign':'center'}  # message placeholder
                )
            ]
        ),

        dcc.Location(id="redirect-after-reg", refresh=True),
        dcc.Store(id='registered-user', data={}, storage_type='session'),
        dcc.Store(id='active-user', data="", storage_type='session'),
        dcc.Store(id='current-user', data="", storage_type='session'),

    ])


# ----------------------------
# Switch tab content (unchanged)
# ----------------------------
@app.callback(
    Output("register-login-content", "children"),
    Input("register-login-tabs", "active_tab"),
    allow_dudplicate=True
)
def switch_register_login(active_tab):
    if active_tab == "tab-register":
        return html.Div([
            dcc.Input(
                id='reg-name', type='text', placeholder='Full Name',
                style={'width':'100%','padding':'12px','borderRadius':'8px','border':'1px solid #2b6fd3','marginBottom':'10px','boxSizing':'border-box'}
            ),
            dcc.Input(
                id='reg-email', type='email', placeholder='Email',
                style={'width':'100%','padding':'12px','borderRadius':'8px','border':'1px solid #2b6fd3','marginBottom':'10px','boxSizing':'border-box'}
            ),
            dcc.Input(
                id='reg-password', type='password', placeholder='Password',
                style={'width':'100%','padding':'12px','borderRadius':'8px','border':'1px solid #2b6fd3','marginBottom':'10px','boxSizing':'border-box'}
            ),
            dcc.Input(
                id='reg-phone', type='text', placeholder='Phone (07xxxxxxxx)',
                style={'width':'100%','padding':'12px','borderRadius':'8px','border':'1px solid #2b6fd3','marginBottom':'10px','boxSizing':'border-box'}
            ),
            dcc.Dropdown(
                id='reg-subscription',
                options=[
                    {'label': '3-Day Free Trial', 'value': 'trial'},
                    {'label': 'Monthly (KES 5)', 'value': 'monthly'},
                    {'label': 'Lifetime (KES 50)', 'value': 'lifetime'}
                ],
                placeholder="Select subscription plan",
                style={'width':'100%','backgroundColor':'#0f1720','color':'red','borderRadius':'8px','padding':'6px','marginBottom':'10px','boxSizing':'border-box'}
            ),
            html.Button(
                'Register & Pay', id='register-btn', n_clicks=0,
                style={'borderRadius':'10px','width':'100%','padding':'12px','background':'#28a745','color':'white','fontWeight':'700','fontSize':'15px'}
            )
        ], style={'display':'flex','flexDirection':'column','gap':'8px'})
    else:
        return html.Div([
            dcc.Input(
                id='login-email', type='email', placeholder='Email',
                style={'width':'100%','padding':'12px','borderRadius':'8px','border':'1px solid #2b6fd3','marginBottom':'10px','boxSizing':'border-box'}
            ),
            dcc.Input(
                id='login-password', type='password', placeholder='Password',
                style={'width':'100%','padding':'12px','borderRadius':'8px','border':'1px solid #2b6fd3','marginBottom':'10px','boxSizing':'border-box'}
            ),
            html.Button(
                'Login', id='login-btn', n_clicks=0,
                style={'borderRadius':'10px','width':'100%','padding':'12px','background':'#1f6feb','color':'white','fontWeight':'700'}
            ),
            html.Div(
                id='login-message',
                style={'minHeight': '28px','marginTop':'6px','textAlign':'center'}  # message placeholder
            )
        ], style={'display':'flex','flexDirection':'column','gap':'8px'})

# ----------------------------
# Two small callbacks to let stacked link-buttons switch the hidden tabs
# ----------------------------
@app.callback(
    Output("register-login-tabs", "active_tab"),
    Input("link-register", "n_clicks"),
    Input("link-login", "n_clicks"),
    prevent_initial_call=True
)
def stacked_links_switch(r_clicks, l_clicks):
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate
    clicked = ctx.triggered[0]['prop_id'].split('.')[0]
    if clicked == "link-register":
        return "tab-register"
    return "tab-login"


# Keep your existing scroll-to-login callback if you still want it
#=============================
@app.callback(
    Output("login-section", "style"),
    Input("login-btn", "n_clicks")
)
def scroll_to_login_section(n_clicks):
    if n_clicks and n_clicks > 0:
        return {"marginTop": "50px", "border": "2px solid #1f6feb", "padding": "10px", "borderRadius":"10px"}
    return {"marginTop": "1000px"}
# ----------------------------
# AI Section layout (Centered)
# ----------------------------
def ai_layout():

    return html.Div([
        # Heading
        html.H2(
            "Convert thought into working ideas",
            style={'color': '#58a6ff', 'textAlign': 'center', 'marginBottom': '20px'}
        ),

        # Container for textarea, button, and answer
        html.Div([
            # Textarea
            dcc.Textarea(
                id='user-question-ai-only',
                placeholder='Describe your thought or idea...',
                style={
                    'width': '80%',
                    'height': '200px',
                    'backgroundColor': '#0d1117',
                    'color': 'white',
                    'padding': '12px',
                    'borderRadius': '10px',
                    'border': '1px solid #30363d',
                    'fontSize': '16px',
                    'resize': 'vertical'
                }
            ),

            # Convert Button
            html.Button(
                "Convert",
                id='ai-only-convert',
                n_clicks=0,
                style={
                    'backgroundColor': '#1f6feb',
                    'color': 'white',
                    'padding': '12px 24px',
                    'border': 'none',
                    'borderRadius': '8px',
                    'fontSize': '16px',
                    'fontWeight': '600',
                    'marginTop': '15px',
                    'cursor': 'pointer'
                }
            ),

            # AI Answer Box
            html.Div(
                id='ai-only-answer',
                style={
                    'backgroundColor': '#21262d',
                    'padding': '20px',
                    'borderRadius': '10px',
                    'marginTop': '20px',
                    'width': '80%',
                    'minHeight': '150px',
                    'color': 'white',
                    'fontSize': '15px',
                    'lineHeight': '1.6'
                }
            )

        ], style={
            'display': 'flex',
            'flexDirection': 'column',
            'alignItems': 'center',
            'width': '100%'
        })

    ], style={
        'display': 'flex',
        'flexDirection': 'column',
        'alignItems': 'center',
        'justifyContent': 'center',
        'padding': '40px',
        'backgroundColor': '#0d1117',
        'minHeight': '100vh'
    })

# ----------------------------
# Donation layout — popup modal version
# ----------------------------
def donation_layout():
    return html.Div([

        # Dim background over the page
        html.Div(
            style={
                'position': 'fixed',
                'top': 0,
                'left': 0,
                'width': '100vw',
                'height': '100vh',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'zIndex': 998
            }
        ),

        # Popup window (centered)
        html.Div([
            html.H2("Donate(help us reach more people)", style={'color':'#1f6feb', 'marginBottom':'10px'}),
            html.P("Enter phone number in format 0xxxxxxxxx and amount (KES).", style={'color':'white'}),

            html.Div([
                html.Label(style={'color':'white'}),
                dcc.Input(
                    id='donate-phone',
                    type='text',
                    placeholder='Phone number',
                    style={'width':'60%', 'marginTop':'5px'}
                ),
                html.Br(), html.Br(),

                html.Label(style={'color':'white'}),
                dcc.Input(
                    id='donate-amount',
                    type='number',
                    placeholder='Amount',
                    style={'width':'40%', 'marginTop':'5px'}
                ),
                html.Br(), html.Br(),

                html.Button(
                    "Donate (STK Push)",
                    id='donate-btn',
                    n_clicks=0,
                    style={
                        'backgroundColor':'#1f6feb',
                        'color':'white',
                        'padding':'10px 20px',
                        'border':'none',
                        'borderRadius':'8px',
                        'cursor':'pointer'
                    }
                ),

                html.Div(
                    id='donation-message',
                    style={
                        'marginTop':'12px',
                        'maxWidth':'700px',
                        'wordBreak':'break-word',
                        'color':'lightgreen'
                    }
                )

            ], style={'marginTop':'10px'}),

            # Close button
            html.A(
                "Close",
                href="/",  # go to home page or previous page
                style={
                    'display':'inline-block',
                    'marginTop':'15px',
                    'padding':'8px 20px',
                    'backgroundColor':'#d9534f',
                    'color':'white',
                    'borderRadius':'8px',
                    'textDecoration':'none',
                    'fontWeight':'600'
                }
            )

        ], style={
            'position': 'fixed',
            'top': '50%',
            'left': '50%',
            'transform': 'translate(-50%, -50%)',
            'backgroundColor': '#0d1117',
            'padding': '30px',
            'borderRadius': '12px',
            'width': '400px',
            'maxWidth': '90%',
            'textAlign': 'center',
            'zIndex': 999,
            'boxShadow': '0 0 20px #1f6feb'
        })

    ])

# ----------------------------
# Partnership layout — popup modal version
# ----------------------------
def partnership_layout():
    return html.Div([

        # Dim background over the page
        html.Div(
            style={
                'position': 'fixed',
                'top': 0,
                'left': 0,
                'width': '100vw',
                'height': '100vh',
                'backgroundColor': 'rgba(0,0,0,0.6)',
                'zIndex': 998
            }
        ),

        # Popup window (centered)
        html.Div([
            html.H2("Partnership", style={'color':'#1f6feb', 'marginBottom':'10px'}),
            html.P("This dashboard allows monitoring of M-Pesa transactions across Kenya. It shows TPM, payment-type trends, sector trends, top counties and alerts.", style={'color':'white'}),
            html.H4("Describe Yourself (we'll send this to the partnership inbox)", style={'color':'#58a6ff', 'marginTop':'15px'}),

            # Textarea with glowing edges
            dcc.Textarea(
                id='partner-desc',
                placeholder='Write something about yourself...',
                style={
                    'width': '100%',
                    'height': 150,
                    'borderRadius': '12px',
                    'border': '2px solid #1f6feb',
                    'padding': '10px',
                    'boxShadow': '0 0 8px #1f6feb',
                    'fontSize': '16px',
                    'resize': 'vertical',
                    'transition': 'box-shadow 0.3s ease',
                    'marginTop': '10px'
                }
            ),
            html.Br(),

            # Send button
            html.Button(
                "Send",
                id='partner-send',
                n_clicks=0,
                style={
                    'backgroundColor':'#1f6feb',
                    'color':'white',
                    'padding':'10px 20px',
                    'border':'none',
                    'borderRadius':'12px',
                    'cursor':'pointer',
                    'marginTop':'10px'
                }
            ),

            # Message div
            html.Div(
                id='partner-msg',
                style={
                    'marginTop':'10px',
                    'fontWeight':'bold',
                    'color':'lightgreen'
                }
            ),

            # Close button
            html.A(
                "Close",
                href="/",  # change to previous page if needed
                style={
                    'display':'inline-block',
                    'marginTop':'15px',
                    'padding':'8px 20px',
                    'backgroundColor':'#d9534f',
                    'color':'white',
                    'borderRadius':'8px',
                    'textDecoration':'none',
                    'fontWeight':'600'
                }
            )

        ], style={
            'position': 'fixed',
            'top': '50%',
            'left': '50%',
            'transform': 'translate(-50%, -50%)',
            'backgroundColor': '#0d1117',
            'padding': '30px',
            'borderRadius': '12px',
            'width': '400px',
            'maxWidth': '90%',
            'textAlign': 'center',
            'zIndex': 999,
            'boxShadow': '0 0 20px #1f6feb'
        })

    ])
# -------------------------------------------
# AI Secretary — Financial Control Room Layout (Final Touch)
# -------------------------------------------
def ai_secretary_layout(user_data):

    if not user_data:
        user_data = {"name": "Guest", "subscription": "None", "email": ""}

    name = user_data.get("name", "Guest")
    subscription = user_data.get("subscription", "None")

    return html.Div([

        # ---------------- HEADER ----------------
        html.Div([
            html.H2(
                "🧠 AI Secretary — Financial Control Room",
                style={
                    'color': '#58a6ff',
                    'fontWeight': '700',
                    'fontSize': '32px',
                    'marginBottom': '0px'
                }
            ),
            html.P(
                f"Welcome, {name}  •  Subscription: {subscription}",
                style={
                    'color': '#8b949e',
                    'fontSize': '16px',
                    'marginTop': '6px',
                    'marginBottom': '30px'
                }
            )
        ], style={'textAlign': 'center'}),

        # ---------------- DASHBOARD METRIC CARDS ----------------
        html.Div([
            html.Div(id='card-total-income', style=card_style(final=True)),
            html.Div(id='card-total-expenses', style=card_style(final=True)),
            html.Div(id='card-net-balance', style=card_style(final=True)),
            html.Div(id='card-peak-hour', style=card_style(final=True)),
        ], style={
            'display': 'flex',
            'gap': '15px',
            'marginBottom': '35px',
            'flexWrap': 'wrap',
            'justifyContent': 'center',
            'maxWidth': '1100px'
        }),

        # ---------------- TRANSACTION INPUT AREA ----------------
        html.Div([
            html.Label(
                "Paste Transaction Messages (M-Pesa, Pochi, Till, Paybill, etc.)",
                style={
                    'color': '#c9d1d9',
                    'fontSize': '14px',
                    'fontWeight': '600',
                    'marginBottom': '8px'
                }
            ),

            dcc.Textarea(
                id='ai-secretary-question',
                placeholder=(
                    "Example:\n"
                    "Received Ksh 450 from 0712...\n"
                    "Sent Ksh 1,200 to PAYBILL 400200..."
                ),
                style={
                    'width': '100%',
                    'height': 160,
                    'backgroundColor': '#0d1117',
                    'color': 'white',
                    'padding': '14px',
                    'borderRadius': '12px',
                    'border': '1px solid #30363d',
                    'fontSize': '14px',
                    'resize': 'vertical'
                }
            ),

            html.Button(
                "Analyze Transactions",
                id='ai-secretary-btn',
                style=button_style(final=True)
            )
        ], style=section_style()),

        # ---------------- DAILY CANDLESTICK CHART ----------------
        html.Div([
            dcc.Graph(id='ai-secretary-candlestick')
        ], style=section_style()),

        # ---------------- ALERTS + MAIN REPORT ----------------
        html.Div([

            html.Div(
                id='ai-secretary-alerts',
                style=report_box_style(final=True)
            ),

            html.Div(
                id='ai-secretary-answer',
                style=report_box_style(final=True)
            )

        ], style={'maxWidth': '1100px'}),

    ], style={
        'padding': '35px',
        'backgroundColor': '#0d1117',
        'minHeight': '100vh',
        'color': 'white',
        'display': 'flex',
        'flexDirection': 'column',
        'alignItems': 'center'
    })


# -------------------------------------------
# Reusable Style Helpers (Final Touch)
# -------------------------------------------

def card_style(final=False):
    style = {
        'flex': '1',
        'minWidth': '220px',
        'backgroundColor': '#0f1115',
        'padding': '20px',
        'borderRadius': '14px',
        'textAlign': 'center',
        'border': '1px solid #30363d',
        'color': 'white',
        'boxShadow': '0 4px 10px rgba(0,0,0,0.3)' if final else ''
    }
    return style


def button_style(final=False):
    style = {
        'marginTop': '12px',
        'padding': '14px 26px',
        'backgroundColor': '#1f6feb',
        'border': '1px solid #265dcf',
        'color': 'white',
        'fontWeight': '600',
        'borderRadius': '12px',
        'cursor': 'pointer',
        'fontSize': '15px',
        'transition': 'all 0.3s',
    }
    if final:
        style['boxShadow'] = '0 4px 8px rgba(0,0,0,0.2)'
        style['hover'] = {'backgroundColor': '#0d4fbb'}
    return style


def section_style():
    return {
        'backgroundColor': '#161b22',
        'padding': '24px',
        'borderRadius': '14px',
        'border': '1px solid #30363d',
        'marginBottom': '35px',
        'maxWidth': '1100px',
        'width': '100%',
        'boxShadow': '0 4px 12px rgba(0,0,0,0.2)'
    }


def report_box_style(final=False):
    style = {
        'backgroundColor': '#1c2128',
        'color': 'white',
        'padding': '22px',
        'borderRadius': '14px',
        'border': '1px solid #30363d',
        'marginBottom': '25px',
        'fontSize': '15px',
        'lineHeight': '1.6',
        'boxShadow': '0 4px 12px rgba(0,0,0,0.25)' if final else ''
    }
    return style

# ----------------------------
# Page Router (lock removed)
# ----------------------------
@app.callback(
    Output('page-content', 'children'),
    Input('url', 'pathname'),
    State('registered-user', 'data'),
    State('active-user', 'data')
)
def display_page(pathname, users_dict, active_user):
    # Ensure dict exists
    if users_dict is None:
        users_dict = {}

    # Determine current user (if any)
    current_user = users_dict.get(active_user, {}) if active_user else {}

    # ----------------------------
    # Public pages
    # ----------------------------
    if pathname == '/register':
        return registration_layout()
    elif pathname == '/donation':
        return donation_layout()
    elif pathname == '/partnership':
        return partnership_layout()
    elif pathname == '/':
        return dashboard_layout()

    # ----------------------------
    # Protected pages (lock removed)
    # ----------------------------
    if pathname == '/ai':
        return ai_layout()

    if pathname == '/ai_secretary':
        return ai_secretary_layout(current_user)

    # ----------------------------
    # Fallback
    # ----------------------------
    return html.Div([
        html.H1("404 - Page not found"),
        dcc.Link("Go Home", href="/")
    ])

# ======================================================
# Combined Registration & Login Callback
# ======================================================
@app.callback(
    Output('registered-user', 'data'),
    Output('active-user', 'data'),
    Output('register-message', 'children'),
    Output('login-message', 'children'),
    Output('redirect-after-reg', 'href'),
    Input('register-btn', 'n_clicks'),
    Input("login-btn", "n_clicks"),
    State('reg-name', 'value'),
    State('reg-email', 'value'),
    State('reg-password', 'value'),
    State('reg-subscription', 'value'),
    State('reg-phone', 'value'),
    State('login-email', 'value'),
    State('login-password', 'value'),
    State('registered-user', 'data'),
    prevent_initial_call=True
)
def handle_auth(reg_clicks, login_clicks, reg_name, reg_email, reg_password,
                reg_subscription, reg_phone, login_email, login_password,
                users_dict):

    # Ensure users_dict exists
    if not isinstance(users_dict, dict):
        users_dict = {}

    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # ---------- Registration ----------
    if triggered_id == "register-btn":
        if not all([reg_name, reg_email, reg_password, reg_subscription, reg_phone]):
            return users_dict, no_update, "⚠️ All registration fields are required.", "", no_update

        email_l = reg_email.lower()
        if email_l in users_dict:
            return users_dict, no_update, "⚠️ An account with that email already exists.", "", no_update

        # Free trial / subscription
        trial_days = 3
        subscription_type = reg_subscription.lower()
        amount_int = 0 if subscription_type=="trial" else (5 if subscription_type=="monthly" else 50)

        # Phone cleanup
        phone = str(reg_phone).strip()
        if phone.startswith("07") or phone.startswith("01"):
            phone = "254" + phone[1:]
        elif not phone.startswith("254"):
            return users_dict, no_update, "⚠️ Invalid phone number format.", "", no_update

        # Payment if needed
        if amount_int > 0:
            result = lipa_na_mpesa_stk_push(
                phone_number=phone,
                amount=amount_int,
                account_reference="Subscription",
                transaction_desc=f"{reg_subscription.capitalize()} Subscription for {reg_name}"
            )
            if not result or not result.get("success"):
                return users_dict, no_update, html.Div([
                    html.Strong("❌ STK Push failed. Please try again."),
                    html.Br(),
                    html.Pre(str(result.get("error") if result else "Unknown error"))
                ]), "", no_update

        # Save user
        saved = add_user(reg_name, email_l, reg_password, reg_subscription, phone, trial_days)
        if not saved:
            return users_dict, no_update, "❌ Failed to register user.", "", no_update

        # Update in-memory store
        users_dict[email_l] = {
            'name': reg_name,
            'password_hash': hash_password(reg_password),
            'phone': phone,
            'subscription': reg_subscription,
            'trial_days': trial_days
        }

        success_msg = html.Div([
            html.Strong(f"✅ Registration successful for {reg_name}."),
            html.Br(),
            html.Span("Free trial for 3 days" if subscription_type=="trial" else f"Check your phone to pay KES {amount_int}.")
        ])

        # Auto-login immediately
        return users_dict, email_l, success_msg, "", "/ai_secretary"

    # ---------- Login ----------
    elif triggered_id == "login-btn":
        if not login_email or not login_password:
            return users_dict, no_update, "", "⚠️ Enter both email and password.", no_update

        email_l = login_email.lower()
        user = users_dict.get(email_l)
        if user and user.get("password_hash") == hash_password(login_password):
            success_msg = html.Div([
                html.Strong(f"✅ Logged in as {user.get('name')}!"),
                html.Br(),
                html.Span("Redirecting...")
            ])
            return users_dict, email_l, "", success_msg, "/ai_secretary"

        return users_dict, no_update, "", "❌ Invalid email or password.", no_update

    # Default return
    return users_dict, no_update, "", "", no_update

# ----------------------------
# Donation callback - performs STK push (sandbox)
# ----------------------------
@app.callback(
    Output('donation-message','children'),
    Input('donate-btn','n_clicks'),
    State('donate-phone','value'),
    State('donate-amount','value')
)
def perform_donation(n_clicks, phone, amount):
    if not n_clicks or n_clicks == 0:
        return ""

    # -------------------------
    # Validate phone
    # -------------------------
    if not phone:
        return "⚠️ Please enter a phone number."
    phone_str = str(phone).strip()
    if not (phone_str.startswith("0") and len(phone_str) >= 10):
        return "⚠️ Phone number must be in format 0xxxxxxxxx."

    # Convert to 254 format
    phone_254 = "254" + phone_str[1:]

    # -------------------------
    # Validate amount
    # -------------------------
    try:
        if not amount or str(amount).strip() == "":
            amount_int = 100  # Default donation
        else:
            amount_int = int(amount)
            if amount_int <= 0:
                return "⚠️ Amount must be a positive number."
    except Exception:
        return "⚠️ Invalid amount entered."

    # -------------------------
    # Perform STK Push
    # -------------------------
    res = lipa_na_mpesa_stk_push(
        phone_number=phone_254,
        amount=amount_int,
        account_reference="Donation",
        transaction_desc="Donation"
    )

    # -------------------------
    # Check for response
    # -------------------------
    if not res:
        return "❌ Failed to send STK push: no response received."

    if not res.get("success"):
        error_msg = res.get("error", "Unknown error")
        return html.Div([
            html.Div("❌ Failed to send STK push (sandbox)."),
            html.Pre(str(error_msg))
        ])

    # -------------------------
    # Success
    # -------------------------
    resp = res.get("response", {})
    return html.Div([
        html.Div("✅ STK Push request sent (sandbox). Check your phone for prompt."),
        html.Pre(json.dumps(resp, indent=2))
    ])

# ----------------------------
# Partnership callback (secure & dynamic)
# ----------------------------
@app.callback(
    Output('partner-msg', 'children'),
    Input('partner-send', 'n_clicks'),
    State('partner-desc', 'value'),
    State('registered-user', 'data'),  # Get logged-in user info
    prevent_initial_call=True
)
def send_partnership_request(n, description, user_data):
    if not description or description.strip() == "":
        return "⚠️ Please write something before sending."

    # Sender info
    default_sender_email = "denisgitari082@gmail.com"   # Your Gmail
    sender_name = user_data.get('name', 'Anonymous') if user_data else 'Anonymous'
    sender_email = default_sender_email               # SMTP login must be your Gmail

    try:
        msg = EmailMessage()
        msg['Subject'] = "New Partnership Request"
        msg['From'] = f"{sender_name} <{default_sender_email}>"
        msg['To'] = "denisgitari082@gmail.com"           # Your inbox
        msg['Reply-To'] = user_data.get('email', default_sender_email) if user_data else default_sender_email
        msg.set_content(f"Partnership Description:\n\n{description}\n\nSender Info:\nName: {sender_name}\nEmail: {user_data.get('email','Not Provided') if user_data else 'Not Provided'}")

        # SMTP login using App Password
        app_password = "hyzj zhdn unov yimx"  # <-- Replace with Gmail App Password
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(default_sender_email, app_password)
            smtp.send_message(msg)

        return "✅ Your partnership request has been sent successfully!"

    except Exception as e:
        return f"❌ Failed to send request: {str(e)}"
#--------------------------------------------------------
#backspace company
#=============================
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from dash import dcc, html, Input, Output


# Global variables
alert_log = []
prev_tpm = None  # sliding buffer for TPM



# ----------------------------
# Process transactions
# ----------------------------
def process_transactions(transactions, county, prev_tpm=None):
    """
    Returns 60-min dashboard data with past preserved and sliding Forex-style trend.
    prev_tpm: previous df_tpm to preserve past.
    """
    now = datetime.now()
    minutes = pd.date_range(end=now, periods=60, freq='min')

    if not transactions:
        # Use previous TPM if exists, otherwise synthetic
        if prev_tpm is not None:
            tpm = prev_tpm['tpm'].to_numpy()
            # slide one step and add new random point
            tpm = np.roll(tpm, -1)
            tpm[-1] = np.clip(tpm[-2] + np.random.randint(-50, 50), 200, 1200)
        else:
            base = np.linspace(300, 800, 60)
            noise = np.random.normal(0, 50, 60)
            tpm = np.clip(base + noise, 200, 1200).astype(int)
        df_tpm = pd.DataFrame({'datetime': minutes, 'tpm': tpm})
    else:
        df = pd.DataFrame(transactions)
        df['datetime'] = pd.to_datetime(df['timestamp'])
        cutoff = now - timedelta(minutes=60)
        df = df[df['datetime'] >= cutoff]
        df_tpm = df.groupby(pd.Grouper(key='datetime', freq='min')).size().reindex(minutes, fill_value=0).reset_index()
        df_tpm.rename(columns={0: 'tpm'}, inplace=True)

    # Payment trend
    payment_trend = pd.DataFrame({
        'datetime': df_tpm['datetime'],
        'Mpesa': df_tpm['tpm']*0.5,
        'Airtel Money': df_tpm['tpm']*0.3,
        'Bank Transfer': df_tpm['tpm']*0.2
    }).melt(id_vars='datetime', var_name='Payment Type', value_name='Transactions')

    # Sector trend
    sector_trend = []
    for _, row in df_tpm.iterrows():
        dist = np.random.dirichlet(np.ones(len(sectors))) * row['tpm']
        entry = dict(zip(sectors, dist))
        entry['datetime'] = row['datetime']
        sector_trend.append(entry)
    sector_trend = pd.DataFrame(sector_trend).melt(id_vars='datetime', value_vars=sectors,
                                                   var_name='Sector', value_name='Transactions')

    # Peak hour heatmap
    df_tpm['hour'] = df_tpm['datetime'].dt.hour
    heatmap = df_tpm.groupby('hour')['tpm'].sum().reset_index()

    # Top counties
    top_counties = pd.DataFrame({
        'County': counties,
        'Transactions': np.random.randint(1000, 5000, len(counties))
    }).sort_values('Transactions', ascending=False).head(5)

    return df_tpm, payment_trend, sector_trend, heatmap, top_counties

# ----------------------------
# Dashboard callback
# ----------------------------
# ensure this global is defined once at top of file:
# prev_tpm = None

@app.callback(
    [Output('tpm-chart','figure'),
     Output('payment-chart','figure'),
     Output('sector-chart','figure'),
     Output('top-counties-chart','figure'),
     Output('top-sectors-chart','figure'),
     Output('peak-hour-heatmap','figure'),
     Output('alert-log','children')],
    [Input('region-dropdown','value'),
     Input('interval-update','n_intervals')],
    prevent_initial_call=True
)
def update_dashboard(county, n):
    import numpy as np
    import plotly.express as px
    import plotly.graph_objects as go
    from datetime import datetime

    global alert_log, prev_tpm

    try:
        token = get_mpesa_oauth_token()
        transactions = []  # replace with real fetch when available
    except Exception:
        transactions = []

    # get processed data
    df_tpm, payment_trend, sector_trend, heatmap, top_counties = process_transactions(
        transactions, county, prev_tpm if 'prev_tpm' in globals() else None
    )

    # update sliding buffer
    prev_tpm = df_tpm.copy()

    # --- Build OHLC for candlestick ---
    df = df_tpm.sort_values('datetime').reset_index(drop=True).copy()
    df['open'] = df['tpm'].shift(1).fillna(df['tpm'].iloc[0])
    df['close'] = df['tpm']

    idx = np.arange(len(df))
    base_vol = np.clip(df['tpm'] * 0.02, 1.0, None)  # 2% volatility, min 1
    wiggle = np.abs(np.sin(idx * 0.37))  # deterministic waveform
    vol = base_vol * (0.5 + 0.5 * wiggle)
    df['high'] = np.maximum(df['open'], df['close']) + vol
    df['low']  = np.minimum(df['open'], df['close']) - vol
    df['low']  = df['low'].clip(lower=0)  # no negative transactions

    # --- Plotly candlestick ---
    tpm_fig = go.Figure(data=[go.Candlestick(
        x=df['datetime'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing_line_color='#26a69a',
        decreasing_line_color='#ef5350',
        name='TPM'
    )])

    tpm_fig.update_layout(
        template='plotly_dark',
        title=f"{county} — Transactions per Minute (Candlesticks)",
        xaxis_title="Time",
        yaxis_title="Transactions",
        xaxis_rangeslider_visible=False,
        xaxis=dict(
            showline=True,
            showgrid=True,
            showticklabels=True,
            tickformat="%H:%M",
            tickangle=45
        ),
        margin=dict(l=10, r=10, t=40, b=60),
        height=420
    )

    # --- Other figures ---
    payment_fig = px.line(payment_trend, x='datetime', y='Transactions',
                          color='Payment Type', template='plotly_dark',
                          title=f"{county} Payment Type Trend")

    sector_fig = px.area(sector_trend, x='datetime', y='Transactions',
                         color='Sector', template='plotly_dark',
                         title=f"{county} Sector Trend")

    heat_fig = px.bar(heatmap, x='hour', y='tpm',
                      template='plotly_dark',
                      title=f"{county} Peak Hour Heatmap")

    top_counties_fig = px.bar(top_counties, x='County', y='Transactions',
                              template='plotly_dark', title="Top Counties")

    top_sectors = sector_trend.groupby('Sector')['Transactions'].sum().sort_values(
        ascending=False).head(5).reset_index()

    top_sectors_fig = px.bar(top_sectors, x='Sector', y='Transactions',
                             text='Transactions', template='plotly_dark',
                             title=f"Top 5 Sectors in {county}")
    top_sectors_fig.update_traces(marker_color="#ff6f58", textposition="outside")

    # --- Alerts ---
    last_tpm = df_tpm['tpm'].iloc[-1]
    avg_tpm = df_tpm['tpm'].rolling(10).mean().iloc[-1]
    diff = (last_tpm - avg_tpm) / avg_tpm * 100 if avg_tpm > 0 else 0
    alert = "🚀 Spike!" if diff > 30 else "📉 Drop!" if diff < -50 else "✅ Stable"
    if diff > 50 or diff < -50:
        timestamp = datetime.now().strftime("%H:%M:%S")
        alert_log.append(f"{timestamp} - {county}: {alert}")
    alert_log = alert_log[-5:]
    alert_log_display = html.Ul([html.Li(a) for a in alert_log])

    return tpm_fig, payment_fig, sector_fig, top_counties_fig, top_sectors_fig, heat_fig, alert_log_display
# ----------------------------
# AI Assistant callbacks
# ----------------------------
@app.callback(
    Output('ai-answer','children'),
    [Input('ask-btn','n_clicks')],
    [State('user-question','value'),
     State('region-dropdown','value')]
)
def ai_assistant_on_dashboard(n, q, county):
    if not n or not q:
        return ""
    avg_tpm = np.random.randint(500,3000)
    total_amount = np.random.randint(1_000_000,20_000_000)
    last_tpm = np.random.randint(500,3000)
    ql = q.lower()
    if 'average' in ql:
        return f"Average transactions per minute in {county}: {avg_tpm:,}."
    if 'total' in ql:
        return f"Total amount processed in {county} today: KES {total_amount:,}."
    if 'current' in ql or 'latest' in ql:
        return f"Current transactions per minute in {county}: {last_tpm:,}."
    return "Try asking about average, total, or current transactions."
# ============================
# AI IDEAS CALLBACK — Genius & Wise Mode with Full Sectors
# ============================
@app.callback(
    Output('ai-only-answer', 'children'),
    Input('ai-only-convert', 'n_clicks'),
    State('user-question-ai-only','value')
)
def ai_only_convert(n, text):
    if not n or not text:
        return ""

    text_lower = text.lower()
    lines = []
    lines.append(html.H4("Your Custom Business Idea & Plan", style={'marginTop':'0', 'color':'#58a6ff'}))

    # -------------------------
    # Detect Business Type — FULL SECTORS
    # -------------------------
    idea = "General Business"
    if any(word in text_lower for word in ['retail','shop','store']):
        idea = "Retail / Store business"
    elif any(word in text_lower for word in ['food','restaurant','cafe','mama mboga']):
        idea = "Food & Beverage"
    elif any(word in text_lower for word in ['transport','taxi','delivery','boda']):
        idea = "Transport & Delivery Service"
    elif any(word in text_lower for word in ['clothing','fashion','tailor']):
        idea = "Fashion & Clothing"
    elif any(word in text_lower for word in ['agriculture','farm','produce']):
        idea = "Agriculture / Farming"
    elif any(word in text_lower for word in ['online','internet','digital']):
        idea = "Online / Digital Service"
    elif any(word in text_lower for word in ['education','school','training']):
        idea = "Education / Training"
    elif any(word in text_lower for word in ['health','clinic','pharmacy']):
        idea = "Health & Wellness"
    elif any(word in text_lower for word in ['entertainment','music','movies','cinema']):
        idea = "Entertainment & Leisure"
    elif any(word in text_lower for word in ['tourism','travel','hotel','guesthouse']):
        idea = "Tourism / Hospitality"
    elif any(word in text_lower for word in ['construction','building','contractor','renovation']):
        idea = "Construction & Real Estate"
    elif any(word in text_lower for word in ['cleaning','laundry','housekeeping']):
        idea = "Cleaning & Maintenance Services"
    elif any(word in text_lower for word in ['consulting','advisory','business plan']):
        idea = "Consulting / Professional Services"

    lines.append(html.Li(f"Business Type: {idea}"))

    # -------------------------
    # Extract Budget
    # -------------------------
    nums = re.findall(r'[\d,]+', text)
    budget = 0
    if nums:
        budget = int(nums[0].replace(',', ''))

    if budget <= 0:
        lines.append(html.Li("⚠️ Budget too low or zero. Start small, scale gradually."))
        budget_info = "Flexible / minimal capital"
    else:
        lines.append(html.Li(f"Suggested starting budget: Ksh {budget:,}"))
        budget_info = f"Ksh {budget:,}"

    # -------------------------
    # Generate Practical Steps Dynamically
    # -------------------------
    steps = []

    if idea == "Transport & Delivery Service":
        if budget <= 0:
            steps = [
                "Start with walking or bicycle deliveries",
                "Offer services to neighbors and friends to gain experience",
                "Save any earnings to upgrade transport gradually"
            ]
        else:
            steps = [
                f"Start with a vehicle or boda boda (budget: {budget_info})",
                "Plan routes efficiently for maximum earnings",
                "Keep a simple log of trips, costs, and profits",
                "Focus on reliability and punctuality"
            ]
    elif idea == "Food & Beverage":
        if budget <= 0:
            steps = [
                "Start with homemade snacks or small meals",
                "Test demand among friends or neighbors",
                "Reinvest profits into expanding menu gradually"
            ]
        else:
            steps = [
                "Choose one type of dish/menu to start",
                f"Use budget efficiently: {budget_info} for raw materials",
                "Advertise locally via word-of-mouth and social media",
                "Keep quality consistent"
            ]
    elif idea == "Retail / Store business":
        if budget <= 0:
            steps = [
                "Start selling popular small items",
                "Track every sale to learn what sells",
                "Gradually increase inventory as profits come in"
            ]
        else:
            steps = [
                "Stock products in demand in your area",
                f"Allocate budget wisely: {budget_info} for initial inventory",
                "Keep track of sales and expenses",
                "Reinvest profits into more profitable items"
            ]
    elif idea == "Fashion & Clothing":
        steps = [
            "Start with small clothing items or tailoring services",
            "Focus on quality over quantity",
            "Ask customers for feedback on styles and fit",
            "Display products where potential customers can easily see them"
        ]
    elif idea == "Agriculture / Farming":
        steps = [
            "Start with crops or animals suitable for your land and climate",
            "Keep simple records of expenses and harvest",
            "Sell to local markets first",
            "Consider crop rotation or multiple small-scale projects"
        ]
    elif idea == "Online / Digital Service":
        steps = [
            "Identify a problem people face online",
            "Offer a simple solution that can be explained easily",
            "Start small and improve gradually based on feedback",
            "Use free or cheap platforms to reach your first customers"
        ]
    elif idea == "Education / Training":
        steps = [
            "Offer a short course or tutoring in something you know well",
            "Start with a few students and ask for referrals",
            "Keep materials simple and practical",
            "Gradually expand subjects or classes based on demand"
        ]
    elif idea == "Health & Wellness":
        steps = [
            "Provide one focused service first, like basic checkups or wellness tips",
            "Keep records of clients and appointments",
            "Offer reliable and affordable services",
            "Ask clients for suggestions on improvements"
        ]
    elif idea == "Entertainment & Leisure":
        steps = [
            "Start small: music lessons, local shows, or streaming content",
            "Test what entertains your target audience",
            "Collaborate with other entertainers",
            "Track revenues and expenses"
        ]
    elif idea == "Tourism / Hospitality":
        steps = [
            "Start with small guesthouses, tours, or travel consultancy",
            "Focus on exceptional customer service",
            "Advertise locally and online",
            "Track bookings, customer feedback, and costs"
        ]
    elif idea == "Construction & Real Estate":
        steps = [
            "Offer small construction or renovation services first",
            "Partner with suppliers for affordable materials",
            "Keep detailed records of costs and profits",
            "Build trust through quality workmanship"
        ]
    elif idea == "Cleaning & Maintenance Services":
        steps = [
            "Start with residential cleaning or laundry services",
            "Use low-cost marketing (flyers, referrals)",
            "Track jobs, time, and income",
            "Gradually expand to commercial clients"
        ]
    elif idea == "Consulting / Professional Services":
        steps = [
            "Offer advice in a field you know well",
            "Start with a few clients and gather feedback",
            "Charge reasonable rates initially",
            "Gradually expand services as reputation grows"
        ]
    else:
        # Default practical steps for other businesses
        if budget <= 0:
            steps = [
                "Start extremely small-scale using creativity over capital",
                "Offer free trials or minimal-cost services",
                "Focus on learning, building reputation, and saving profits"
            ]
        else:
            steps = [
                f"Use budget {budget_info} to start practical, simple operations",
                "Track all costs and earnings carefully",
                "Iterate and improve your offering based on feedback"
            ]

    lines.append(html.Li("Practical Steps to Start:"))
    lines.append(html.Ul([html.Li(step) for step in steps]))

    # -------------------------
    # Growth Advice & Warnings
    # -------------------------
    lines.append(html.Li("Tips for Growth & Sustainability:"))
    growth_tips = [
        "Reinvest profits carefully and gradually scale operations",
        "Listen to customers and adjust your offerings",
        "Maintain quality, reliability, and transparency",
        "Collaborate or network with other local businesses",
        "If budget is extremely low, focus on services or ideas that need minimal capital"
    ]
    lines.append(html.Ul([html.Li(tip) for tip in growth_tips]))

    # -------------------------
    # Bonus: rough predictions
    # -------------------------
    lines.append(html.Li("Rough Estimates (if budget > 0):"))
    if budget > 0:
        est_profit = max(int(budget * 0.05), 50)  # 5% daily profit or at least 50 Ksh
        est_expense = int(budget * 0.02)          # 2% daily expense
        lines.append(html.Ul([
            html.Li(f"Expected daily revenue: ~Ksh {budget + est_profit:,}"),
            html.Li(f"Expected daily expenses: ~Ksh {est_expense:,}"),
            html.Li(f"Expected net profit/day: ~Ksh {est_profit - est_expense:,}")
        ]))
    else:
        lines.append(html.Ul([
            html.Li("Revenue & profit depend entirely on effort and customer base"),
            html.Li("Start small, track, and reinvest profits gradually")
        ]))

    return html.Div(lines, style={'padding':'12px', 'lineHeight':'1.6', 'fontSize':'15px'})

# ==============================
# AI Secretary — CONTROL ROOM CALLBACK
# ==============================

live_transactions = []


def parse_message(msg):
    """Parse incoming text for MPESA-like transactions."""
    text = msg['text'].lower()
    dt = msg['datetime']

    # Detect finance transaction keywords
    if any(k in text for k in ['mpesa', 'pochi', 'paybill', 'till', 'sent', 'received']):
        amount = extract_amount(text)

        # INCOME
        if any(k in text for k in ['received', 'credited']):
            live_transactions.append({
                'datetime': dt,
                'type': 'income',
                'amount': amount
            })

        # EXPENSE
        elif any(k in text for k in ['sent', 'paid', 'debited']):
            live_transactions.append({
                'datetime': dt,
                'type': 'expense',
                'amount': amount
            })


def extract_amount(text):
    nums = re.findall(r'[\d,]+', text)
    if nums:
        return int(nums[0].replace(",", ""))
    return 0

# ===================================
# AI Secretary — PRO Callback (Per Transaction Candles)
# ===================================

live_transactions = []

def parse_message(msg):
    """Parse message for mpesa-like transactions"""
    text = msg['text'].lower()
    dt = msg['datetime']

    if any(k in text for k in ['mpesa', 'pochi', 'paybill', 'till','received','sent','credited','debited','paid']):
        amount = extract_amount(text)

        if 'received' in text or 'credited' in text:
            live_transactions.append({'datetime': dt, 'type': 'income', 'amount': amount})
        elif 'sent' in text or 'paid' in text or 'debited' in text:
            live_transactions.append({'datetime': dt, 'type': 'expense', 'amount': amount})

def extract_amount(text):
    nums = re.findall(r'[\d,]+', text)
    if nums:
        return int(nums[0].replace(",", ""))
    return 0

# -----------------------------
# MAIN CALLBACK
# -----------------------------
@app.callback(
    Output('ai-secretary-answer', 'children'),
    Output('ai-secretary-candlestick', 'figure'),
    Output('card-total-income', 'children'),
    Output('card-total-expenses', 'children'),
    Output('card-net-balance', 'children'),
    Output('card-peak-hour', 'children'),

    Input('ai-secretary-btn', 'n_clicks'),
    State('ai-secretary-question', 'value'),
    State('registered-user', 'data')
)
def ai_secretary_live(n, text_input, user_data):

    # -------------------------
    # User info
    # -------------------------
    if not user_data:
        user_data = {"name": "Guest", "subscription": "None", "email": ""}

    name = user_data.get("name", "Guest")
    subscription = user_data.get("subscription", "None")

    # -------------------------
    # Parse messages
    # -------------------------
    if text_input:
        for line in text_input.split("\n"):
            if line.strip():
                parse_message({"text": line, "datetime": datetime.now()})

    if not live_transactions:
        empty_fig = go.Figure()
        empty_fig.update_layout(template='plotly_dark')
        return (
            "Waiting for transaction messages…",
            empty_fig,
            "Ksh 0",
            "Ksh 0",
            "Ksh 0",
            "---"
        )

    # -------------------------
    # Build DataFrame per transaction
    # -------------------------
    df = pd.DataFrame(live_transactions)
    df['income'] = df['amount'].where(df['type']=='income', 0)
    df['expense'] = df['amount'].where(df['type']=='expense', 0)

    # Compute cumulative balance for each transaction
    df['net_change'] = df['income'] - df['expense']
    df['balance'] = df['net_change'].cumsum()
    df['open'] = df['balance'] - df['net_change']
    df['close'] = df['balance']
    df['high'] = df[['open','close']].max(axis=1)
    df['low'] = df[['open','close']].min(axis=1)

    # -------------------------
    # Candlestick Figure
    # -------------------------
    fig = go.Figure(data=[go.Candlestick(
        x=df['datetime'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        increasing_line_color='green',
        decreasing_line_color='red',
        showlegend=False
    )])
    fig.update_layout(
        template='plotly_dark',
        title=f"Transaction-wise Financial Candlesticks — {name}",
        xaxis_title="Time",
        yaxis_title="Balance (KES)"
    )

    # -------------------------
    # Summary Cards
    # -------------------------
    total_income = df['income'].sum()
    total_expenses = df['expense'].sum()
    net_balance = total_income - total_expenses
    peak_hour = df.groupby(df['datetime'].dt.hour)['income'].sum().idxmax()

    # -------------------------
    # AI Insights
    # -------------------------
    insights = []

    if net_balance < 0:
        insights.append("⚠️ Expenses exceed income — adjust your budget.")
    if df['income'].max() > df['income'].mean() * 2:
        insights.append("🚀 Major income spike detected — review source.")
    if df['expense'].max() > df['expense'].mean() * 2:
        insights.append("🔴 High spending spike detected — investigate.")

    if not insights:
        insights.append("✅ Transactions look normal today.")

    insight_div = html.Div([
        html.H4("AI Insights & Alerts", style={'color':'#58a6ff','marginBottom':'8px'}),
        html.Ul([html.Li(i) for i in insights])
    ], style={'padding':'10px'})

    # -------------------------
    # Return all outputs with labels for cards
    # -------------------------
    return (
        insight_div,
        fig,
        html.Div([
            html.P("Total Income", style={'color':'#8b949e','marginBottom':'4px'}),
            html.H4(f"Ksh {total_income:,}", style={'color':'lime','margin':'0'})
        ], style={'textAlign':'center'}),
        html.Div([
            html.P("Total Expenses", style={'color':'#8b949e','marginBottom':'4px'}),
            html.H4(f"Ksh {total_expenses:,}", style={'color':'red','margin':'0'})
        ], style={'textAlign':'center'}),
        html.Div([
            html.P("Net Balance", style={'color':'#8b949e','marginBottom':'4px'}),
            html.H4(f"Ksh {net_balance:,}", style={'color':'cyan','margin':'0'})
        ], style={'textAlign':'center'}),
        html.Div([
            html.P("Peak Income Hour", style={'color':'#8b949e','marginBottom':'4px'}),
            html.H4(f"{peak_hour}:00", style={'color':'yellow','margin':'0'})
        ], style={'textAlign':'center'})
    )

# ----------------------------
# ----------------------------
# STK Push Function
# ----------------------------
def lipa_na_mpesa_stk_push(phone_number, amount, account_reference, transaction_desc):
    # your STK push implementation here
    # return {"success": True, "response": response_data}
    pass


# ----------------------------
# Database Helpers
# ----------------------------
def add_user_simple(name, email, password, subscription):
    # ...
    pass

def email_exists(email):
    # ...
    pass

def activate_user(phone, amount):
    # ...
    pass

from flask import request, jsonify

# ----------------------------
# M-Pesa STK Push Callback Endpoint  ✅ ADD THIS SECTION HERE
# ----------------------------
from flask import request, jsonify

@app.server.route("/mpesa_callback", methods=["POST"])
def mpesa_callback():
    try:
        data = request.get_json()

        callback = data.get("Body", {}).get("stkCallback", {})

        result_code = callback.get("ResultCode")
        result_desc = callback.get("ResultDesc")

        if result_code == 0:
            amount = None
            phone = None

            metadata = callback.get("CallbackMetadata", {}).get("Item", [])
            for item in metadata:
                name = item.get("Name")
                if name == "Amount":
                    amount = item.get("Value")
                elif name == "PhoneNumber":
                    phone = str(item.get("Value"))

            if phone:
                activate_user(phone, amount)
                print(f"✅ Payment confirmed for {phone}: KES {amount}")
            else:
                print("⚠️ Payment callback received but phone number missing.")
        else:
            print(f"❌ Payment failed: {result_desc}")

        return jsonify({"ResultCode": 0, "ResultDesc": "Callback received successfully"})

    except Exception as e:
        print("❌ Callback Error:", str(e))
        return jsonify({"ResultCode": 1, "ResultDesc": "Callback processing error"})
# --------------------------------------
# Search Engine Callback
# --------------------------------------
@app.callback(
    Output('search-results', 'children'),
    Input('search-btn', 'n_clicks'),
    State('search-bar', 'value'),
    State('region-dropdown', 'value')
)
def search_dashboard(n, query, county):
    if not n or not query:
        return ""

    query = query.lower().strip()

    # Generate fresh dashboard data
    df_tpm, payment_trend, sector_trend, heatmap, top_counties = process_transactions([], county)

    results = []

    # --- SEARCH COUNTIES ---
    for c in counties:
        if query in c.lower():
            results.append(f"County Match: {c}")

    # --- SEARCH TPM (numbers) ---
    for _, row in df_tpm.iterrows():
        if query in str(row['tpm']).lower():
            results.append(f"TPM Match: {row['datetime']} = {row['tpm']}")

    # --- SEARCH PAYMENT TRENDS ---
    for _, row in payment_trend.iterrows():
        if query in row['Payment Type'].lower():
            results.append(f"Payment Match: {row['Payment Type']} at {row['datetime']}")

    # --- SEARCH SECTORS ---
    for _, row in sector_trend.iterrows():
        if query in row['Sector'].lower():
            results.append(f"Sector Match: {row['Sector']} at {row['datetime']}")

    # --- SEARCH HOURS (Heatmap) ---
    for _, row in heatmap.iterrows():
        if query in str(row['hour']):
            results.append(f"Peak Hour Match: Hour {row['hour']} → {row['tpm']} TPM")

    # --- SEARCH TOP COUNTIES ---
    for _, row in top_counties.iterrows():
        if query in row['County'].lower():
            results.append(f"Top County Match: {row['County']} ({row['Transactions']} transactions)")

    if not results:
        return "❌ No matches found."

    return html.Ul([html.Li(r) for r in results])

# ----------------------------
# Run app
# ----------------------------
if __name__ == '__main__':
    app.run_server(host="0.0.0.0", port=8050)
