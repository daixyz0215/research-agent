import re
from datetime import datetime

import streamlit as st
from openai import OpenAI
from fpdf import FPDF


# =========================
# 基本設定
# =========================
st.set_page_config(page_title="Research Agent", layout="wide")
st.title("Research Agent")
st.caption("調査計画 → 調査実行 → レビュー → PDFダウンロード")

client = OpenAI()

FONT_PATH = "fonts/NotoSansJP-VariableFont_wght.ttf"


# =========================
# 補助関数
# =========================
def normalize_text_for_pdf(text: str) -> str:
    """
    PDFで文字化けしやすい記号を置換する。
    """
    if not text:
        return ""

    replacements = {
        "—": "-",
        "–": "-",
        "−": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "•": "-",
        "→": "->",
        "■": "[■]",
        "□": "[□]",
        "▲": "[▲]",
        "▼": "[▼]",
        "\u00a0": " ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def build_pdf_bytes(query: str, plan: str, report: str) -> bytes:
    """
    調査テーマ、調査計画、最終レポートをPDF化して返す。
    """
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.add_font("NotoSansJP", fname=FONT_PATH)
    pdf.set_font("NotoSansJP", size=16)

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # タイトル
    pdf.multi_cell(0, 10, "Research Report")
    pdf.ln(2)

    pdf.set_font("NotoSansJP", size=11)
    pdf.multi_cell(0, 7, f"作成日時: {created_at}")
    pdf.multi_cell(0, 7, f"調査テーマ: {normalize_text_for_pdf(query)}")
    pdf.ln(3)

    # 調査計画
    pdf.set_font("NotoSansJP", size=14)
    pdf.multi_cell(0, 9, "調査計画")
    pdf.ln(1)

    pdf.set_font("NotoSansJP", size=11)
    pdf.multi_cell(0, 7, normalize_text_for_pdf(plan))
    pdf.ln(4)

    # 最終レポート
    pdf.set_font("NotoSansJP", size=14)
    pdf.multi_cell(0, 9, "最終レポート")
    pdf.ln(1)

    pdf.set_font("NotoSansJP", size=11)
    pdf.multi_cell(0, 7, normalize_text_for_pdf(report))

    return bytes(pdf.output())


def sanitize_filename(text: str) -> str:
    """
    ダウンロード用ファイル名に使えない文字を除去する。
    """
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = text.strip()
    return text[:50] if text else "research_report"


def run_research_agent(query: str) -> tuple[str, str]:
    """
    3段階:
    1. 調査計画
    2. 調査実行（Web検索あり）
    3. レビュー
    """
    with st.spinner("1/3 調査計画を作成中..."):
        plan_res = client.responses.create(
            model="gpt-5.4",
            input=f"""
あなたは優秀なリサーチプランナーです。
次のテーマについて、調査計画を作成してください。

調査テーマ:
{query}

要件:
- まず調査目的を明確にする
- 次に重要な調査観点を3〜5個出す
- 最後に追加確認すべき点を挙げる
- 日本語で書く

出力形式:
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
次の調査テーマについて、与えられた調査計画に厳密に従って調査してください。

調査テーマ:
{query}

調査計画:
{plan_text}

ルール:
- 必要に応じてWeb検索を使う
- 信頼できる情報を優先する
- 事実と解釈を分ける
- 情報が弱い場合は断定しない
- できるだけ具体的に書く
- 日本語で書く

出力形式:
## 要約
## 主要ファクト
## 解釈
## 示唆
## 参考ソース
"""
        )
        draft_report = research_res.output_text

    with st.spinner("3/3 不足点をレビュー中..."):
        review_res = client.responses.create(
            model="gpt-5.4",
            input=f"""
あなたは厳格なレビュアーです。
次のレポートをレビューし、曖昧な部分や不足があれば補って、読みやすい最終版に整えてください。

調査テーマ:
{query}

調査計画:
{plan_text}

下書きレポート:
{draft_report}

要件:
- 日本語で書く
- 内容を整理して読みやすくする
- 調査計画とのズレがあれば修正する
- 不足が明確な場合のみ「不足している点」として最後に書く

出力形式:
## 最終レポート
## 不足している点
- なければ「特になし」
"""
        )
        final_report = review_res.output_text

    return plan_text, final_report


# =========================
# セッション状態
# =========================
if "history" not in st.session_state:
    st.session_state.history = []

if "latest_result" not in st.session_state:
    st.session_state.latest_result = None


# =========================
# UI
# =========================
query = st.text_input(
    "調査テーマ",
    placeholder="例: 日本の生成AI導入の最新動向 / 競合A社とB社の比較 / 英語学習アプリ市場の動向"
)

col1, col2 = st.columns([1, 1])

with col1:
    run_button = st.button("調査開始", use_container_width=True)

with col2:
    clear_button = st.button("履歴をクリア", use_container_width=True)

if clear_button:
    st.session_state.history = []
    st.session_state.latest_result = None
    st.success("履歴をクリアしました。")

if run_button:
    if not query.strip():
        st.warning("調査テーマを入力してください。")
    else:
        try:
            plan_text, final_report = run_research_agent(query.strip())

            result = {
                "query": query.strip(),
                "plan": plan_text,
                "report": final_report,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }

            st.session_state.latest_result = result
            st.session_state.history.insert(0, result)

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

st.divider()

# =========================
# 最新結果の表示
# =========================
if st.session_state.latest_result:
    latest = st.session_state.latest_result

    st.subheader("最終レポート")
    st.caption(f"作成日時: {latest['created_at']}")
    st.write(latest["report"])

    try:
        pdf_bytes = build_pdf_bytes(
            query=latest["query"],
            plan=latest["plan"],
            report=latest["report"],
        )

        filename = f"{sanitize_filename(latest['query'])}.pdf"

        st.download_button(
            label="PDFをダウンロード",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"PDF生成でエラーが発生しました: {e}")

    with st.expander("調査計画を見る"):
        st.write(latest["plan"])

else:
    st.info("まだ実行結果はありません。調査テーマを入力して「調査開始」を押してください。")

st.divider()

# =========================
# 履歴表示
# =========================
if st.session_state.history:
    st.subheader("過去の実行結果")

    for i, item in enumerate(st.session_state.history, start=1):
        with st.expander(f"{i}. {item['query']} ({item['created_at']})"):
            st.markdown("**最終レポート**")
            st.write(item["report"])

            st.markdown("**調査計画**")
            st.write(item["plan"])
