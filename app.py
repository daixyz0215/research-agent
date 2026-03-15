import streamlit as st
from openai import OpenAI

st.title("Research Agent")

client = OpenAI()

query = st.text_input("調査テーマ")

if st.button("調査開始"):

    response = client.responses.create(
        model="gpt-5.4",
        tools=[{"type": "web_search"}],
        input=f"""
あなたはResearch Agentです。

次のテーマを調査してください。

テーマ:
{query}

条件
・必要に応じてWeb検索
・出典付き
・要点を箇条書き
"""
    )

    st.write(response.output_text)
