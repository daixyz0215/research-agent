import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Research Agent", layout="wide")
st.title("Research Agent")

client = OpenAI()

query = st.text_input("調査テーマ", placeholder="例: 日本の生成AI導入の最新動向")

if "history" not in st.session_state:
    st.session_state.history = []

if st.button("調査開始"):
    if not query.strip():
        st.warning("調査テーマを入力してください。")
    else:
        with st.spinner("1/3 調査計画を作成中..."):
            plan_res = client.responses.create(
                model="gpt-5.4",
                input=f"""
あなたは優秀なリサーチプランナーです。
次のテーマについて、調査計画を作ってください。

テーマ:
{query}

以下の形式で出力してください。
## 調査目的
## 調査観点
- 観点1
- 観点2
- 観点3
## 追加で確認すべき点
- 点1
- 点2
"""
            )
            plan_text = plan_res.output_text

        with st.spinner("2/3 調査を実行中..."):
            research_res = client.responses.create(
                model="gpt-5.4",
                tools=[{"type": "web_search"}],
                input=f"""
あなたは Research Agent です。
次の調査計画に厳密に従って調査してください。

調査テーマ:
{query}

調査計画:
{plan_text}

ルール:
- 必要に応じてWeb検索を使う
- 信頼できる情報を優先する
- 事実と解釈を分ける
- 出典が弱い情報は断定しない

出力形式:
## 要約
## 主要ファクト
## 解釈
## 参考ソース
"""
            )
            draft_report = research_res.output_text

        with st.spinner("3/3 不足点をチェック中..."):
            review_res = client.responses.create(
                model="gpt-5.4",
                input=f"""
あなたは厳格なレビュアーです。
次の調査レポートを見て、不足や曖昧さがあれば補ってください。

調査テーマ:
{query}

調査計画:
{plan_text}

調査レポート:
{draft_report}

次の形式で出力してください。
## 最終レポート
## このレポートで不足している点
- なければ「特になし」
"""
            )
            final_report = review_res.output_text

        st.session_state.history.insert(0, {
            "query": query,
            "plan": plan_text,
            "report": final_report
        })

st.divider()

if st.session_state.history:
    latest = st.session_state.history[0]

    st.subheader("最終レポート")
    st.write(latest["report"])

    with st.expander("調査計画を見る"):
        st.write(latest["plan"])

    with st.expander("過去の実行結果"):
        for i, item in enumerate(st.session_state.history, start=1):
            st.markdown(f"### {i}. {item['query']}")
            st.write(item["report"])
else:
    st.info("まだ実行結果はありません。")
