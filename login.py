import os
import msal
import streamlit as st
import socket

CLIENT_ID = st.secrets["AZURE_CLIENT_ID"]
CLIENT_SECRET = st.secrets["AZURE_CLIENT_SECRET"]
TENANT_ID = st.secrets["AZURE_TENANT_ID"]

local_ip = socket.gethostbyname(socket.gethostname())
is_server = local_ip == "10.10.20.3"

if is_server:
    st.config.set_option("server.port", 8056)
    st.config.set_option("server.sslCertFile", "cert/cert.pem")
    st.config.set_option("server.sslKeyFile", "cert/key.pem")
else:
    st.config.set_option("server.port", 8501)

st.config.set_option("server.enableCORS", False)
st.config.set_option("server.enableXsrfProtection", False)
st.config.set_option("server.headless", True)

REDIRECT_URI = st.secrets["AZURE_REDIRECT_URI_SERVER"] if is_server else st.secrets["AZURE_REDIRECT_URI_LOCAL"]

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["User.Read"]

def build_msal_app():
    return msal.ConfidentialClientApplication(
        CLIENT_ID,
        authority=AUTHORITY,
        client_credential=CLIENT_SECRET,
    )

def get_auth_url():
    return build_msal_app().get_authorization_request_url(
        SCOPES,
        redirect_uri=REDIRECT_URI,
    )

def exchange_code_for_token(code):
    return build_msal_app().acquire_token_by_authorization_code(
        code,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )

def render_report(filter_string=""):
    embed_url = "https://app.powerbi.com/reportEmbed?reportId=c03466a4-103f-42aa-9225-597cd5ce1a25&autoAuth=true&ctid=31c347a9-3e62-4167-b697-eacfb065e074"
    if filter_string:
        embed_url += f"&filter={filter_string}"

    st.markdown(f"""
        <div style="width:100%; height:85vh; overflow:hidden;">
            <iframe title="CRT - Personal Activity Report" 
            style="width:100%; height:100%; border:none;"
            src="{embed_url}" 
            allowFullScreen="true"></iframe>
        </div>
    """, unsafe_allow_html=True)