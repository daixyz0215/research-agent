import os
import re
import textwrap
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

FONT_PATH = "fonts/NotoSansJP-Regular.ttf"


# =========================
# OpenAI client
# =========================
@st.cache_resource
def get_client():
    return OpenAI()


client = get_client()


# =========================
# 補助関数
# =========================
def sanitize_filename(text: str) -> str:
    text = re.sub(r'[\\/:*?"<>|]+', "_", text)
    text = text.strip()
    return text[:50] if text else "research_report"


def normalize_text_for_pdf(text: str) -> str:
    if not text:
        return ""

    replacements = {
        "\u00a0": " ",
        "—": "-",
        "–": "-",
        "−": "-",
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "•": "-",
        "●": "-",
        "○": "-",
        "▪": "-",
        "■": "[■]",
        "□": "[□]",
        "▲": "[▲]",
        "▼": "[▼]",
        "→": "->",
        "←": "<-",
        "※": "*",
        "\t": "    ",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def wrap_long_tokens(text: str, width: int = 60) -> str:
    """
    URLや改行不能な長い文字列でPDFが崩れるのを防ぐ。
    """
    lines = []
    for line in text.split("\n"):
        if not line.strip():
            lines.append("")
            continue

        parts = line.split(" ")
        new_parts = []
        for part in parts:
            if len(part) > width:
                new_parts.append("\n".join(textwrap.wrap(part, width=width, break_long_words=True)))
            else:
                new_parts.append(part)
        lines.append(" ".join(new_parts))
    return "\n".join(lines)


def safe_pdf_text(text: str) -> str:
    text = normalize_text_for_pdf(text)
    text = wrap_long_tokens(text, width=60)
    return text


def add_multiline_text(pdf: FPDF, text: str, line_height: float = 7.0):
    """
    FPDFの横幅不足エラーを避けるため、安全な幅で1行ずつ描画する。
    """
    usable_width = pdf.w - pdf.l_margin - pdf.r_margin
    if usable_width <= 20:
        raise ValueError("PDFの描画幅が不足しています。")

    for raw_line in safe_pdf_text(text).split("\n"):
        line = raw_line if raw_line else " "
        pdf.multi_cell(
            w=usable_width,
            h=line_height,
            text=line,
            new_x="LMARGIN",
            new_y="NEXT",
        )


def build_pdf_bytes(query: str, plan: str, report: str) -> bytes:
    if not os.path.exists(FONT_PATH):
        raise FileNotFoundError(
            f"フォントファイルが見つかりません: {FONT_PATH}"
        )

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_left_margin(15)
    pdf.set_right_margin(15)
    pdf.set_top_margin(15)
    pdf.add_page()

    pdf.add_font("NotoSansJP", fname=FONT_PATH)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # タイトル
    pdf.set_font("NotoSansJP", size=16)
    add_multiline_text(pdf, "Research Report", line_height=10)
    pdf.ln(2)

    pdf.set_font("NotoSansJP", size=11)
    add_multiline_text(pdf, f"作成日時: {created_at}")
    add_multiline_text(pdf, f"調査テーマ: {query}")
    pdf.ln(3)

    # 調査計画
    pdf.set_font("NotoSansJP", size=14)
    add_multiline_text(pdf, "調査計画", line_height=9)
    pdf.ln(1)

    pdf.set_font("NotoSansJP", size=11)
    add_multiline_text(pdf, plan)
    pdf.ln(4)

    # 最終レポート
    pdf.set_font("NotoSansJP", size=14)
    add_multiline_text(pdf, "最終レポート", line_height=9)
    pdf.ln(1)

    pdf.set_font("NotoSansJP", size=11)
    add_multiline_text(pdf, report)

    return bytes(pdf.output())


def run_research_agent(query: str) -> tuple[str, str]:
    with st.spinner("1/3 調査計画を作成中..."):
        plan_res = client.responses.create(
            model="gpt-5.4",
            input=f"""
あなたは優秀なリサーチプランナーです。
次のテーマについて、調査計画を作成してください。

調査テーマ:
{query}

要件:
- 調査目的を明確にする
- 重要な調査観点を3〜5個出す
- 追加確認すべき点を挙げる
- 日本語で書く
- 簡潔だが実務で使える内容にする

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
次の調査テーマについて、与えられた調査計画に従って調査してください。

調査テーマ:
{query}

調査計画:
{plan_text}

ルール:
- 必要に応じてWeb検索を使う
- 信頼できる情報を優先する
- 事実と解釈を分ける
- 情報が弱い場合は断定しない
- 日本語で書く
- 実務で使える粒度で整理する
- 可能な限り参考ソースを付ける

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
- 不足が明確な場合のみ最後に記載する
- 過剰に長くしすぎない

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

col1, col2 = st.columns(2)

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
# 最新結果
# =========================
if st.session_state.latest_result:
    latest = st.session_state.latest_result

    st.subheader("最終レポート")
    st.caption(f"作成日時: {latest['created_at']}")
    st.markdown(latest["report"])

    try:
        pdf_bytes = build_pdf_bytes(
            query=latest["query"],
            plan=latest["plan"],
            report=latest["report"],
        )

        st.download_button(
            label="PDFをダウンロード",
            data=pdf_bytes,
            file_name=f"{sanitize_filename(latest['query'])}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"PDF生成でエラーが発生しました: {e}")

    with st.expander("調査計画を見る"):
        st.markdown(latest["plan"])
else:
    st.info("まだ実行結果はありません。調査テーマを入力して「調査開始」を押してください。")

st.divider()

# =========================
# 履歴
# =========================
if st.session_state.history:
    st.subheader("過去の実行結果")

    for i, item in enumerate(st.session_state.history, start=1):
        with st.expander(f"{i}. {item['query']} ({item['created_at']})"):
            st.markdown("**最終レポート**")
            st.markdown(item["report"])
            st.markdown("**調査計画**")
            st.markdown(item["plan"])
