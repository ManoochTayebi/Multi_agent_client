"""Optional Streamlit client; the primary UI is served directly by FastAPI."""
import os
import httpx
import streamlit as st

st.set_page_config(page_title='Atlas CustomerAI',page_icon='✳',layout='wide')
st.title('Atlas CustomerAI')
st.caption('Six-agent retail demonstration · fictional data · simulated payments')
base = os.environ.get('ATLAS_API_URL','http://localhost:8000')
customer = st.sidebar.selectbox('Customer',['C0001','C0002','C0007'])
credential = st.sidebar.text_input('Customer credential (protected mode)',type='password')
if st.sidebar.button('Start session'):
    r = httpx.post(base+'/api/sessions',json={'customer_id':customer},
                   headers={'Authorization':'Bearer '+credential} if credential else {},timeout=20)
    if r.is_success:
        st.session_state.token = r.json()['token']
        st.session_state.history = []
    else:
        st.error(r.text)
for item in st.session_state.get('history',[]):
    with st.chat_message(item['role']):
        st.write(item['text'])
prompt = st.chat_input('Return O1001, or build an outfit under EUR 150')
if prompt:
    if not st.session_state.get('token'):
        st.warning('Start a session first.')
    else:
        with st.spinner('Coordinating specialists…'):
            r = httpx.post(base+'/api/chat',headers={'Authorization':'Bearer '+st.session_state.token},
                           json={'message':prompt},timeout=180)
        if r.is_success:
            result = r.json()
            st.session_state.history.extend([{'role':'user','text':prompt},
                                            {'role':'assistant','text':result['answer']}])
            st.write(result['answer'])
            st.json({'trace':result['trace'],'quality':result['quality'],'action':result['action']})
        else:
            st.error(r.text)
