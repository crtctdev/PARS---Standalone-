import os
import msal
import requests
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

def check_pars_group_membership(user_oid):
    token_resp = requests.post(
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": "https://graph.microsoft.com/.default",
        },
    )
    if token_resp.status_code != 200:
        return False
    headers = {"Authorization": f"Bearer {token_resp.json().get('access_token')}"}

    group_resp = requests.get(
        "https://graph.microsoft.com/v1.0/groups?$filter=displayName eq 'PARS - Security'&$select=id",
        headers=headers,
    )
    if group_resp.status_code != 200:
        return False
    groups_found = group_resp.json().get("value", [])
    if not groups_found:
        return False
    group_id = groups_found[0]["id"]

    members_url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members?$select=id"
    while members_url:
        resp = requests.get(members_url, headers=headers)
        if resp.status_code != 200:
            return False
        data = resp.json()
        if any(m["id"] == user_oid for m in data.get("value", [])):
            return True
        members_url = data.get("@odata.nextLink")
    return False


def render_report(filter_string=""):
    import streamlit.components.v1 as components

    embed_url = "https://app.powerbi.com/reportEmbed?reportId=c03466a4-103f-42aa-9225-597cd5ce1a25&autoAuth=true&ctid=31c347a9-3e62-4167-b697-eacfb065e074"
    if filter_string:
        embed_url += f"&filter={filter_string}"

    st.markdown(f"""
        <style>
            @media print {{
                body * {{ visibility: hidden !important; }}
                #pbi-report-wrap, #pbi-report-wrap * {{ visibility: visible !important; }}
                #pbi-report-wrap {{
                    position: fixed !important;
                    top: 0; left: 0;
                    width: 100% !important; height: 100% !important;
                }}
                #pbi-print-btn {{ display: none !important; }}
            }}
        </style>
        <div id="pbi-report-wrap" style="width:100%; height:85vh; overflow:hidden;">
            <iframe title="CRT - Personal Activity Report"
            style="width:100%; height:100%; border:none;"
            src="{embed_url}"
            allowFullScreen="true"></iframe>
        </div>
    """, unsafe_allow_html=True)

    components.html("""
    <script>
    (function() {
        var doc = window.parent.document;
        if (doc.getElementById('pbi-print-btn')) return;
        var btn = doc.createElement('button');
        btn.id = 'pbi-print-btn';
        btn.textContent = '\\uD83D\\uDDA8 Print report';
        btn.style.cssText = 'position:fixed; top:64px; right:28px; z-index:9999;' +
            'padding:6px 14px; cursor:pointer; border:1px solid #2d3f55;' +
            'border-radius:6px; background:#3b82f6; color:#fff;' +
            'font-size:13px; font-weight:500;';
        btn.onclick = function() { window.parent.print(); };
        doc.body.appendChild(btn);
    })();
    </script>
    """, height=0)