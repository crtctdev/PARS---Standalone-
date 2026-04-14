import msal
import streamlit as st

CLIENT_ID = st.secrets["AZURE_CLIENT_ID"]
CLIENT_SECRET = st.secrets["AZURE_CLIENT_SECRET"]
TENANT_ID = st.secrets["AZURE_TENANT_ID"]
REDIRECT_URI = st.secrets["AZURE_REDIRECT_URI"]

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