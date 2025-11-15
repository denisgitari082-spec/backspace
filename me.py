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
sectors = ['Transport','Communication','Retail','Banking','Government','Utilities']

app = Dash(__name__)
app.title = "MoodSync Kenya Dashboard - Live M-Pesa"

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
CALLBACK_URL = "https://your-public-callback-url.example.com/mpesa_callback"

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

def add_user(full_name, email, password, subscription):
    users = load_users()
    timestamp = datetime.datetime.utcnow().isoformat() + "Z"
    user = {
        "full_name": full_name,
        "email": email,
        "password_hash": hash_password(password),
        "subscription": subscription,
        "registered_at": timestamp
    }
    users.append(user)
    save_users(users)

# ----------------------------
# M-Pesa STK Push (Sandbox)
# ----------------------------
def get_mpesa_oauth_token():
    """
    Retrieves OAuth token from the sandbox.
    """
    url = f"{https://sandbox.safaricom.co.ke}/oauth/v1/generate?grant_type=client_credentials"
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
    timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    password_str = SHORTCODE + PASSKEY + timestamp
    password = base64.b64encode(password_str.encode()).decode()
    url = f"{https://sandbox.safaricom.co.ke}/mpesa/stkpush/v1/processrequest"
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
        "CallBackURL": CALLBACK_URL,
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
    dcc.Store(id='registered-user', storage_type='session'),
html.Div([
    dcc.Link("Dashboard", href="/", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("Registration", href="/register", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("AI Section", href="/ai", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("Donation", href="/donation", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("Partnership", href="/partnership", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'}),
    dcc.Link("AI Secretary", href="/ai_secretary", style={'padding':'12px 16px','color':'white','textDecoration':'none','fontWeight':'600'})
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
 # placeholders for dynamically created IDs
    html.Button(id='ai-secretary-btn', style={'display': 'none'}),
    html.Button(id='ai-only-convert', style={'display': 'none'}),
    html.Button(id='ask-btn', style={'display': 'none'}),
    dcc.Interval(id='interval-update', interval=1000, n_intervals=0),
    html.Button(id='partner-send', style={'display': 'none'}),
    html.Button(id='donate-btn', style={'display': 'none'}),
    html.Button(id='register-btn', style={'display': 'none'}),
    html.Div(id='page-content')
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
# Registration + Login layout
# ----------------------------
def registration_layout():
    return html.Div([

        # Dark semi-transparent background
        html.Div(
            id="registration-modal-background",
            style={
                "position": "fixed",
                "top": "0",
                "left": "0",
                "width": "100%",
                "height": "100%",
                "backgroundColor": "rgba(0,0,0,0.6)",
                "display": "flex",
                "justifyContent": "center",
                "alignItems": "center",
                "zIndex": "999",
                "overflow": "auto"
            },
            children=[html.Div(
                id="registration-modal",
                style={
                    "backgroundColor": "#0d1117",
                    "borderRadius": "12px",
                    "padding": "20px",
                    "width": "90%",
                    "maxWidth": "400px",
                    "maxHeight": "85vh",
                    "overflowY": "auto",
                    "boxShadow": "0 0 25px rgba(0,0,0,0.35)",
                    "textAlign": "center",
                    "color": "white",
                    "display": "flex",
                    "flexDirection": "column",
                    "alignItems": "center",
                    "gap": "10px"
                },
                children=[

                    html.H2("Welcome", style={'color': '#58a6ff', 'marginBottom': '20px'}),

                    # Tabs for Register / Login
                    dbc.Tabs(
                        [
                            dbc.Tab(label="Register", tab_id="tab-register"),
                            dbc.Tab(label="Login", tab_id="tab-login"),
                        ],
                        id="register-login-tabs",
                        active_tab="tab-register",
                        className="mb-3",
                    ),

                    # Dynamic form content (register or login)
                    html.Div(id="register-login-content", style={'width': '100%'}),

                    # Close button → navigate home
                    html.A(
                        "Close",
                        href="/",  # change to previous page if needed
                        style={
                            'display':'block',
                            'textDecoration':'none',
                            'borderRadius': '10px',
                            'width': '100%',
                            'padding': '12px',
                            'background': '#d9534f',
                            'color': 'white',
                            'fontWeight': '600',
                            'fontSize': '16px',
                            'marginTop': '10px',
                            'textAlign': 'center'
                        }
                    ),

                    # Messages (for both login & register)
                    html.Div(id='register-message', style={'marginTop': '15px', 'color': '#ff6f58', 'fontWeight':'600'})
                ]
            )]
        ),

        # Hidden login section for real navigation
        html.Div(id='login-section', style={'marginTop':'1000px'}, children=[
            html.H2("Login Section"),
            dcc.Input(id='login-section-email', type='email', placeholder='Email',
                      style={'width':'100%','padding':'10px','marginBottom':'10px'}),
            dcc.Input(id='login-section-password', type='password', placeholder='Password',
                      style={'width':'100%','padding':'10px','marginBottom':'10px'}),
            html.Button('Submit Login', id='login-section-btn', n_clicks=0,
                        style={'width':'100%','padding':'12px','background':'#1f6feb','color':'white','fontWeight':'600','borderRadius':'10px'})
        ]),

        dcc.Store(id='registered-user', data={})
    ])

# ----------------------------
# Switch tab content
# ----------------------------
@app.callback(
    Output("register-login-content", "children"),
    Input("register-login-tabs", "active_tab")
)
def switch_register_login(active_tab):
    if active_tab == "tab-register":
        return html.Div([
            dcc.Input(id='reg-name', type='text', placeholder='Full Name',
                      style={'width':'100%','padding':'10px','borderRadius':'8px','border':'1px solid #58a6ff','marginBottom':'10px'}),
            dcc.Input(id='reg-email', type='email', placeholder='Email',
                      style={'width':'100%','padding':'10px','borderRadius':'8px','border':'1px solid #58a6ff','marginBottom':'10px'}),
            dcc.Input(id='reg-password', type='password', placeholder='Password',
                      style={'width':'100%','padding':'10px','borderRadius':'8px','border':'1px solid #58a6ff','marginBottom':'10px'}),
            dcc.Input(id='reg-phone', type='text', placeholder='Phone (07xxxxxxxx)',
                      style={'width':'100%','padding':'10px','borderRadius':'8px','border':'1px solid #58a6ff','marginBottom':'10px'}),
            dcc.Dropdown(
                id='reg-subscription',
                options=[
                    {'label': '3-Day Free Trial', 'value': 'trial'},
                    {'label': 'Monthly (KES 5)', 'value': 'monthly'},
                    {'label': 'Lifetime (KES 50)', 'value': 'lifetime'}
                ],
                placeholder="Select subscription plan",
                style={'width':'100%','backgroundColor':'#21262d','color':'red','borderRadius':'8px','padding':'5px','marginBottom':'10px'}
            ),
            html.Button('Register & Pay', id='register-btn', n_clicks=0,
                        style={'borderRadius':'10px','width':'100%','padding':'12px','background':'#4CAF50','color':'white','fontWeight':'600','fontSize':'16px'})
        ])
    else:
        # Login tab: scroll to hidden login section when clicked
        return html.Div([
            dcc.Input(id='login-email', type='email', placeholder='Email',
                      style={'width':'100%','padding':'10px','borderRadius':'8px','border':'1px solid #58a6ff','marginBottom':'10px'}),
            dcc.Input(id='login-password', type='password', placeholder='Password',
                      style={'width':'100%','padding':'10px','borderRadius':'8px','border':'1px solid #58a6ff','marginBottom':'10px'}),
            html.Button('Login', id='login-btn', n_clicks=0,
                        style={'borderRadius':'10px','width':'100%','padding':'12px','background':'#1f6feb','color':'white','fontWeight':'600','fontSize':'16px'})
        ])

# ----------------------------
# Login button scroll to login section
# ----------------------------
@app.callback(
    Output("login-section", "style"),
    Input("login-btn", "n_clicks")
)
def scroll_to_login_section(n_clicks):
    if n_clicks and n_clicks > 0:
        # scroll to login section smoothly using CSS trick
        return {"marginTop": "50px", "border": "2px solid #1f6feb", "padding": "10px"}
    return {"marginTop": "1000px"}

# ----------------------------
# AI Section layout (Auto Popup Window — No Callbacks)
# ----------------------------
def ai_layout(registered):

    # -----------------------------------------------
    # USER NOT REGISTERED → Show popup window
    # -----------------------------------------------
    if not registered:
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
                html.H2("Login Required", style={'color': 'red', 'marginBottom': '10px'}),

                html.P(
                    "You must register or login to access the AI Assistant.",
                    style={'color': 'white'}
                ),

                html.P(
                    "Registration is quick — includes a 3-day free trial.",
                    style={'color': '#58a6ff'}
                ),

                dcc.Link(
                    "Open Registration",
                    href="/register",
                    style={
                        'display': 'inline-block',
                        'padding': '10px 20px',
                        'backgroundColor': '#1f6feb',
                        'color': 'white',
                        'borderRadius': '8px',
                        'marginTop': '10px',
                        'textDecoration': 'none',
                        'fontWeight': 'bold'
                    }
                ),

                html.Br(),
                html.Br(),

                dcc.Link(
                    "Close",
                    href="/",
                    style={
                        'display': 'inline-block',
                        'padding': '8px 20px',
                        'backgroundColor': '#444',
                        'color': 'white',
                        'borderRadius': '8px',
                        'textDecoration': 'none'
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
                'width': '340px',
                'textAlign': 'center',
                'zIndex': 999,
                'boxShadow': '0 0 20px #1f6feb'
            })

        ])

    # -----------------------------------------------
    # USER REGISTERED → Normal AI Page
    # -----------------------------------------------
    return html.Div([
        html.H2(
            "AI — Convert thought into working ideas",
            style={'color': '#58a6ff'}
        ),

        dcc.Textarea(
            id='user-question-ai-only',
            placeholder='Describe your thought or idea...',
            style={
                'width': '60%',
                'height': 150,
                'backgroundColor': '#0d1117',
                'color': 'white',
                'marginBottom': '10px'
            }
        ),

        html.Button(
            "Convert",
            id='ai-only-convert',
            n_clicks=0,
            style={
                'backgroundColor': '#1f6feb',
                'color': 'white',
                'padding': '10px',
                'border': 'none',
                'borderRadius': '8px'
            }
        ),

        html.Div(
            id='ai-only-answer',
            style={
                'backgroundColor': '#21262d',
                'padding': '15px',
                'borderRadius': '10px',
                'marginTop': '10px',
                'maxWidth': '800px'
            }
        )
    ])


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
            html.H2("Donation (M-Pesa STK Push - Sandbox)", style={'color':'#1f6feb', 'marginBottom':'10px'}),
            html.P("Enter phone number in format 0xxxxxxxxx and amount (KES). This uses Safaricom sandbox credentials.", style={'color':'white'}),

            html.Div([
                html.Label("Phone Number (0xxxxxxxxx)", style={'color':'white'}),
                dcc.Input(
                    id='donate-phone',
                    type='text',
                    placeholder='0xxxxxxxxx',
                    style={'width':'60%', 'marginTop':'5px'}
                ),
                html.Br(), html.Br(),

                html.Label("Amount (KES)", style={'color':'white'}),
                dcc.Input(
                    id='donate-amount',
                    type='number',
                    placeholder='100',
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
            html.P("Contact: denisgitari082@gmail.com", style={'color':'white'}),
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

# ----------------------------
# AI Secretary layout — upgraded popup for non-registered users
# ----------------------------
def ai_secretary_layout(user_data):

    # -----------------------------------------------
    # USER NOT REGISTERED → Show popup window
    # -----------------------------------------------
    if not user_data or not user_data.get('email'):
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
                html.H2("Login Required", style={'color': '#ff6f58', 'marginBottom': '10px'}),
                html.P("You must register or login to access the AI Secretary.", style={'color': 'white'}),
                html.P("Registration is quick — includes a 3-day free trial.", style={'color': '#58a6ff'}),

                dcc.Link(
                    "Open Registration",
                    href="/register",
                    style={
                        'display': 'inline-block',
                        'padding': '10px 20px',
                        'backgroundColor': '#1f6feb',
                        'color': 'white',
                        'borderRadius': '8px',
                        'marginTop': '10px',
                        'textDecoration': 'none',
                        'fontWeight': 'bold'
                    }
                ),

                html.Br(),
                html.Br(),

                dcc.Link(
                    "Close",
                    href="/",
                    style={
                        'display': 'inline-block',
                        'padding': '8px 20px',
                        'backgroundColor': '#444',
                        'color': 'white',
                        'borderRadius': '8px',
                        'textDecoration': 'none'
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
                'width': '340px',
                'textAlign': 'center',
                'zIndex': 999,
                'boxShadow': '0 0 20px #1f6feb'
            })

        ])

    # -----------------------------------------------
    # USER REGISTERED → Show full AI Secretary dashboard
    # -----------------------------------------------
    return html.Div([
        html.H2("🗂 AI Secretary — Personal Financial Control Room", style={'color':'#58a6ff'}),

        # User input for questions/messages
        dcc.Textarea(
            id='ai-secretary-question',
            placeholder='Paste or type your transaction messages here (mpesa, pochi, paybill, till, received, sent)...',
            style={'width':'60%','height':150,'backgroundColor':'#0d1117','color':'white','marginBottom':'10px'}
        ),
        html.Button(
            "Analyze",
            id='ai-secretary-btn',
            n_clicks=0,
            style={'backgroundColor':'#1f6feb','color':'white','padding':'10px','border':'none','borderRadius':'8px'}
        ),

        # Live graph: income vs expenses
        dcc.Graph(
            id='ai-secretary-income-expenses',
            style={'marginTop':'20px', 'maxWidth':'900px'}
        ),

        # Alerts section
        html.Div(
            id='ai-secretary-alerts',
            style={'backgroundColor':'#21262d','color':'white','padding':'10px','marginTop':'10px','borderRadius':'8px','maxWidth':'900px'}
        ),

        # Main report / advice section
        html.Div(
            id='ai-secretary-answer',
            style={'backgroundColor':'#21262d','color':'white','padding':'10px','marginTop':'10px','borderRadius':'8px','maxWidth':'900px'}
        )
    ])


# ----------------------------
# Page router
# ----------------------------
@app.callback(
    Output('page-content','children'),
    Input('url','pathname'),
    State('registered-user','data')
)
def display_page(pathname, user_data):
    # Fix: make sure user_data is a dict even if None
    if user_data is None:
        user_data = {}

    registered = user_data.get('email') is not None

    if pathname == '/register':
        return registration_layout()
    elif pathname == '/ai':
        return ai_layout(registered)
    elif pathname == '/donation':
        return donation_layout()
    elif pathname == '/partnership':
        return partnership_layout()
    elif pathname == '/ai_secretary':
        return ai_secretary_layout(user_data)
    else:
        return dashboard_layout()
# === user helpers ===
import json, os, hashlib

USERS_FILE = "users.json"

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def load_users():
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception as e:
        print("load_users error:", e)
        return {}

def save_users_dict(users_dict):
    try:
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users_dict, f, indent=2)
        return True
    except Exception as e:
        print("save_users_dict error:", e)
        return False

def add_user(name, email, password, subscription, phone, trial_days):
    """
    Save user with password hash. Returns True on success, False on failure.
    """
    users = load_users()  # dict keyed by email
    email_l = email.lower()
    if email_l in users:
        return False
    users[email_l] = {
        "name": name,
        "email": email_l,
        "password_hash": hash_password(password),
        "subscription": subscription,
        "phone": phone,
        "trial_days": trial_days,
        "registered_at": datetime.datetime.utcnow().isoformat() + "Z"
    }
    return save_users_dict(users)

def check_login(email, password):
    """
    Return user dict on success, None on failure.
    """
    users = load_users()
    if not email:
        return None
    u = users.get(email.lower())
    if not u:
        return None
    if u.get("password_hash") == hash_password(password):
        return u
    return None


# ----------------------------
# Registration Only Callback
# ----------------------------
@app.callback(
    Output('registered-user', 'data'),
    Output('register-message', 'children'),
    Input('register-btn', 'n_clicks'),
    State('reg-name', 'value'),
    State('reg-email', 'value'),
    State('reg-password', 'value'),
    State('reg-subscription', 'value'),
    State('reg-phone', 'value'),
    State('registered-user', 'data'),
    prevent_initial_call=True
)
def handle_registration(reg_clicks,
                        reg_name, reg_email, reg_password, reg_subscription, reg_phone,
                        stored):

    if stored is None:
        stored = {}

    # Only trigger on register button
    if not reg_clicks:
        return stored, ""

    # ----------------------------
    # Validation
    # ----------------------------
    if not all([reg_name, reg_email, reg_password, reg_subscription, reg_phone]):
        return stored, "⚠️ All registration fields are required."

    if reg_email in stored:
        return stored, "⚠️ An account with that email already exists."

    # Free trial: 3 days
    trial_days = 3
    subscription_type = reg_subscription.lower()

    if subscription_type == "monthly":
        amount_int = 5
    elif subscription_type == "lifetime":
        amount_int = 50
    elif subscription_type == "trial":
        amount_int = 0
    else:
        return stored, "⚠️ Invalid subscription type selected."

    # Phone cleanup
    phone = str(reg_phone).strip()
    if phone.startswith("07") or phone.startswith("01"):
        phone = "254" + phone[1:]
    elif not phone.startswith("254"):
        return stored, "⚠️ Invalid phone number format."

    # ----------------------------
    # Payment (only if > 0)
    # ----------------------------
    if amount_int > 0:
        result = lipa_na_mpesa_stk_push(
            phone_number=phone,
            amount=amount_int,
            account_reference="Subscription",
            transaction_desc=f"{reg_subscription.capitalize()} Subscription for {reg_name}"
        )
        if not result or not result.get("success"):
            return (
                stored,
                html.Div([
                    html.Strong("❌ STK Push failed. Please try again."),
                    html.Br(),
                    html.Pre(str(result.get("error") if result else "Unknown error"))
                ])
            )

    # ----------------------------
    # Save user
    # ----------------------------
    try:
        saved = add_user(reg_name, reg_email, reg_password, reg_subscription)
        if not saved:
            return stored, "❌ Failed to register user ."

        # Save in-store for login verification
        stored[reg_email] = {
            'name': reg_name,
            'password': reg_password,
            'phone': phone,
            'subscription': reg_subscription,
            'trial_days': trial_days
        }

        return (
            stored,
            html.Div([
                html.Strong(f"✅ Registration successful for {reg_name}."),
                html.Br(),
                html.Span(
                    "Free trial for 3 days" if subscription_type == "trial"
                    else f"Check your phone to pay KES {amount_int}."
                )
            ])
        )

    except Exception as e:
        return stored, f"Failed to register: {str(e)}"

# ----------------------------
# Login callback (in-memory, works with registered-user store)
# ----------------------------
@app.callback(
    Output("login-message", "children"),
    Input("login-btn", "n_clicks"),
    State("login-email", "value"),
    State("login-password", "value"),
    State("registered-user", "data"),
    prevent_initial_call=True
)
def handle_login(n_clicks, email, password, stored):
    if not n_clicks:
        return no_update

    if not stored:
        stored = {}

    if not email or not password:
        return "⚠️ Enter both email and password."

    user = stored.get(email)
    if user and user.get("password") == password:
        return html.Div([
            html.Strong(f"✅ Logged in as {user.get('name')}!"),
            html.Br(),
            html.Span("You can now access the dashboard.")
        ])
    else:
        return "❌ Invalid email or password."

#-------------------
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
    if not phone or not amount:
        return "Please provide phone number and amount."
    phone_str = str(phone).strip()
    if not (phone_str.startswith("0") and len(phone_str) >= 10):
        return "Phone number must be in format 0xxxxxxxxx."
    try:
        if not amount or str(amount).strip() == "":
            amount_int = 100  # Default donation amount
        else:
            amount_int = int(amount)
            if amount_int <= 0:
                return "Amount must be a positive number."
    except Exception:
        return "Invalid amount."
    res = lipa_na_mpesa_stk_push(phone_str, amount_int, account_reference="Donation", transaction_desc="Donation")
    if not res.get("success"):
        return html.Div([html.Div("Failed to send STK push (sandbox)."), html.Pre(str(res.get("error")))])
    resp = res.get("response", {})
    return html.Div([html.Div("STK Push request sent (sandbox). Check your phone for prompt."), html.Pre(json.dumps(resp, indent=2))])

# ----------------------------
# Partnership callback (use logged-in email)
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

    # Use user's email if available; otherwise use default
    sender_email = user_data.get('email') if user_data and user_data.get('email') else "no-reply@example.com"

    try:
        msg = EmailMessage()
        msg['Subject'] = "New Partnership Request"
        msg['From'] = sender_email              # dynamically set sender
        msg['To'] = "denisgitari@gmail.com"     # your inbox
        msg.set_content(f"Partnership Description:\n\n{description}")

        # SMTP login using your app credentials
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login("denisgitari@gmail.com", "@denis123%")  # App Password for Gmail
            smtp.send_message(msg)

        return "✅ Your partnership request has been sent successfully!"

    except Exception as e:
        return f"❌ Failed to send request: {str(e)}"

# ----------------------------
# Process transactions for dashboard
# ----------------------------
def process_transactions(transactions, county):
    if not transactions:
        minutes = pd.date_range(end=datetime.now(), periods=60, freq='T')
        tpm = np.random.randint(200,1200, size=len(minutes))
        df_tpm = pd.DataFrame({'datetime': minutes, 'tpm': tpm})
    else:
        df = pd.DataFrame(transactions)
        df['datetime'] = pd.to_datetime(df['timestamp'])
        df_tpm = df.groupby(pd.Grouper(key='datetime', freq='T')).size().reset_index(name='tpm')

    payment_trend = pd.DataFrame({
        'datetime': df_tpm['datetime'],
        'Mpesa': df_tpm['tpm']*0.7,
        'Airtel Money': df_tpm['tpm']*0.2,
        'Bank Transfer': df_tpm['tpm']*0.1
    }).melt(id_vars='datetime', var_name='Payment Type', value_name='Transactions')

    sector_trend = []
    for _, row in df_tpm.iterrows():
        dist = np.random.dirichlet(np.ones(len(sectors)))*row['tpm']
        entry = dict(zip(sectors, dist))
        entry['datetime'] = row['datetime']
        sector_trend.append(entry)
    sector_trend = pd.DataFrame(sector_trend).melt(id_vars='datetime', value_vars=sectors, var_name='Sector', value_name='Transactions')

    df_tpm['hour'] = df_tpm['datetime'].dt.hour
    heatmap = df_tpm.groupby('hour')['tpm'].sum().reset_index()

    top_counties = pd.DataFrame({
        'County': counties,
        'Transactions': np.random.randint(1000,5000,len(counties))
    }).sort_values('Transactions', ascending=False).head(5)

    return df_tpm, payment_trend, sector_trend, heatmap, top_counties

# ----------------------------
# Dashboard update callback
# ----------------------------
@app.callback(
    [Output('tpm-chart','figure'),
     Output('payment-chart','figure'),
     Output('sector-chart','figure'),
     Output('top-counties-chart','figure'),
     Output('top-sectors-chart','figure'),
     Output('peak-hour-heatmap','figure'),
     Output('alert-log','children')],
    [Input('region-dropdown','value'),
     Input('interval-update','n_intervals')]
)
def update_dashboard(county, n):
    global alert_log
    try:
        token = get_mpesa_oauth_token()
        # transactions simulation
        transactions = []
    except Exception:
        transactions = []

    df_tpm, payment_trend, sector_trend, heatmap, top_counties = process_transactions(transactions, county)

    tpm_fig = px.line(df_tpm, x='datetime', y='tpm', title=f"{county} - Transactions per Minute", template='plotly_dark')
    payment_fig = px.line(payment_trend, x='datetime', y='Transactions', color='Payment Type', template='plotly_dark', title=f"{county} Payment Type Trend")
    sector_fig = px.area(sector_trend, x='datetime', y='Transactions', color='Sector', template='plotly_dark', title=f"{county} Sector Trend")
    heat_fig = px.bar(heatmap, x='hour', y='tpm', title=f"{county} Peak Hour Heatmap", template='plotly_dark')
    top_counties_fig = px.bar(top_counties, x='County', y='Transactions', template='plotly_dark', title="Top Counties")
    top_sectors = sector_trend.groupby('Sector')['Transactions'].sum().sort_values(ascending=False).head(5).reset_index()
    top_sectors_fig = px.bar(top_sectors, x='Sector', y='Transactions', text='Transactions', template='plotly_dark', title=f"Top 5 Sectors in {county}")
    top_sectors_fig.update_traces(marker_color="#ff6f58", textposition="outside")

    total_txn_val = int(df_tpm['tpm'].sum())
    total_amt_val = int(total_txn_val * 150)
    current_tpm_val = int(df_tpm['tpm'].iloc[-1])

    avg_tpm = df_tpm['tpm'].rolling(10).mean().iloc[-1]
    last_tpm = df_tpm['tpm'].iloc[-1]
    diff = (last_tpm - avg_tpm) / avg_tpm * 100 if avg_tpm > 0 else 0
    alert = "🚀 Spike!" if diff > 50 else "📉 Drop!" if diff < -50 else "✅ Stable"
    if diff > 50 or diff < -50:
        timestamp = datetime.now().strftime("%H:%M:%S")
        alert_log.append(f"{timestamp} - {county}: {alert}")
    alert_log = alert_log[-5:]
    alert_log_display = html.Ul([html.Li(a) for a in alert_log])

    def sparkline(data, color):
        fig = go.Figure()
        fig.add_trace(go.Scatter(y=data, mode='lines', line=dict(color=color, width=1)))
        fig.update_layout(template='plotly_dark', margin=dict(l=0,r=0,t=0,b=0), height=50,
                          xaxis=dict(visible=False), yaxis=dict(visible=False))
        return dcc.Graph(figure=fig, style={'height':'50px'})

    return (tpm_fig, payment_fig, sector_fig, top_counties_fig, top_sectors_fig, heat_fig,
            alert_log_display)

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

@app.callback(
    Output('ai-only-answer','children'),
    Input('ai-only-convert','n_clicks'),
    State('user-question-ai-only','value'),
    State('registered-user','data')
)
def ai_only_convert(n, text, user_data):
    if not n or not text:
        return ""
    if not user_data or not user_data.get('email'):
        return "Please register to use this feature."
    lines = []
    lines.append(html.H4("Converted idea — quick starter", style={'marginTop':'0'}))
    lines.append(html.Ul([
        html.Li("One-sentence summary: " + (text[:120] + ("..." if len(text) > 120 else ""))),
        html.Li("Possible product/service: " + ("A web app / marketplace / API")),
        html.Li("First MVP feature: " + "User registration + core functionality"),
        html.Li("Suggested tech stack: " + "Python (Dash/Flask), PostgreSQL, React (optional)"),
        html.Li("Next steps: " + "Build simple prototype, test with 5 users, iterate")
    ]))
    return html.Div(lines, style={'padding':'8px'})

# ----------------------------
# AI Secretary callback
# ----------------------------
# Live transaction storage
live_transactions = []

def parse_message(msg):
    """Parse message text to detect transactions"""
    text = msg['text'].lower()
    dt = msg['datetime']

    if any(k in text for k in ['mpesa', 'pochi', 'paybill', 'till']):
        amount = extract_amount(text)
        if 'received' in text:
            live_transactions.append({'datetime': dt, 'type': 'income', 'amount': amount})
        elif 'sent' in text:
            live_transactions.append({'datetime': dt, 'type': 'expense', 'amount': amount})

def extract_amount(text):
    """Extract KES amount from message text"""
    nums = re.findall(r'[\d,]+', text)
    if nums:
        return int(nums[0].replace(',', ''))
    return 0

@app.callback(
    Output('ai-secretary-answer', 'children'),
    Input('interval-component', 'n_intervals'),
    State('registered-user', 'data'),
    State('region-dropdown', 'value')
)
def ai_secretary_live(n, user_data, county):
    if not user_data or not user_data.get('email'):
        return "Please register first."

    if not live_transactions:
        return "Waiting for live transactions..."

    # Build DataFrame
    df = pd.DataFrame(live_transactions)
    df['income'] = df['amount'].where(df['type'] == 'income', 0)
    df['expenses'] = df['amount'].where(df['type'] == 'expense', 0)
    df_grouped = df.groupby(pd.Grouper(key='datetime', freq='T')).sum().reset_index()

    # Single Graph: Income vs Expenses
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_grouped['datetime'], y=df_grouped['income'],
                             mode='lines+markers', name='Income', line=dict(color='lime')))
    fig.add_trace(go.Scatter(x=df_grouped['datetime'], y=df_grouped['expenses'],
                             mode='lines+markers', name='Expenses', line=dict(color='red')))
    fig.update_layout(title="Income vs Expenses (Live)",
                      xaxis_title='Time', yaxis_title='KES',
                      template='plotly_dark')

    # Calculations
    total_income = df['income'].sum()
    total_expenses = df['expenses'].sum()
    net_balance = total_income - total_expenses
    peak_hour = df.groupby(df['datetime'].dt.hour)['income'].sum().idxmax()

    # Alerts
    alerts = []
    if net_balance < 0:
        alerts.append("⚠️ Expenses exceed income!")
    if df_grouped['income'].max() > df_grouped['income'].mean() * 1.5:
        alerts.append("🚀 Income spike detected")
    if df_grouped['expenses'].max() > df_grouped['expenses'].mean() * 1.5:
        alerts.append("🔴 High spending detected")
    if not alerts:
        alerts.append("✅ Transactions normal")

    # Response
    response = [
        dcc.Graph(figure=fig),
        html.Div([
            html.P(f"Total income: KES {total_income:,}", style={'color': 'lime'}),
            html.P(f"Total expenses: KES {total_expenses:,}", style={'color': 'red'}),
            html.P(f"Net balance: KES {net_balance:,}", style={'color': 'cyan'}),
            html.P(f"Peak income hour: {peak_hour}:00", style={'color': 'yellow'}),
            html.H5("Alerts & Advice:"),
            html.Ul([html.Li(a) for a in alerts])
        ], style={'padding': '8px', 'backgroundColor': '#1e1e1e', 'borderRadius': '8px'})
    ]
    return html.Div(response)
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
def add_user(name, email, password, subscription):
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
