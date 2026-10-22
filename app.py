import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

st.set_page_config(page_title='MediValue | Healthcare Screener', page_icon='🩺', layout='wide')
BASE=Path(__file__).resolve().parent

@st.cache_data
def load():
    market=pd.read_csv(BASE/'medivalue_market_data.csv')
    latest=pd.read_csv(BASE/'medivalue_latest_financials.csv')
    history=pd.read_csv(BASE/'medivalue_financial_ratios.csv')
    latest['Fiscal_End']=pd.to_datetime(latest['Fiscal_End'],errors='coerce')
    history['Fiscal_End']=pd.to_datetime(history['Fiscal_End'],errors='coerce')
    merged=market.merge(latest,on='Ticker',how='left',suffixes=('_Market',''))
    for c in ['Accruals','Asset_Growth','Debt_to_Assets','ROA','Free_Cash_Flow','PE_Ratio','Price_to_Book','EV_to_EBITDA','Market_Cap']:
        merged[c]=pd.to_numeric(merged[c],errors='coerce')
    return merged,history

df,hist=load()
st.title('🩺 MediValue')
st.caption(st.markdown("""
### Welcome to MediValue!

MediValue is an interactive stock screening tool that helps users explore healthcare companies and identify potential financial warning signs. It analyzes financial performance, valuation ratios, and industry comparisons to generate SELL-risk scores.

**How to use MediValue:** Start by using the sidebar to filter industries and adjust the importance of different financial factors. Explore the rankings, investigate individual companies, and compare up to five stocks side by side. Historical financial data and charts provide additional insight into company performance over time.
""")
)

st.sidebar.header('Screening controls')
industries=sorted(df['Industry'].dropna().unique().tolist())
selected=st.sidebar.multiselect('Industries',industries,default=industries)
min_cap=st.sidebar.number_input('Minimum market capitalization ($ millions)',min_value=0,value=0,step=100)
require_valuation=st.sidebar.checkbox('Require valid positive valuation multiple',value=False)
st.sidebar.subheader('Scoring weights')
w_valuation=st.sidebar.slider('Relative valuation',0,100,40,5)
w_quality=st.sidebar.slider('Earnings quality',0,100,35,5)
w_risk=st.sidebar.slider('Financial vulnerability',0,100,25,5)
if w_valuation+w_quality+w_risk==0:
    st.error('Select at least one positive weight.');st.stop()

# Within-industry percentile scores; a larger number indicates more expensive or more concerning.
# For valuation, negative/nonpositive multiples are excluded, not treated as cheap.
# At least five valid peer observations required for an industry metric.
def within_peer_percentile(frame, column, higher_is_worse=True):
    s=pd.to_numeric(frame[column],errors='coerce')
    valid=s.notna() & np.isfinite(s)
    out=pd.Series(np.nan,index=frame.index,dtype=float)
    for _,indices in frame[valid].groupby('Industry').groups.items():
        v=s.loc[indices]
        if len(v)<5: continue
        ranks=v.rank(pct=True,ascending=higher_is_worse)
        # ascending=True: high raw values -> high percentile; ascending=False: low -> high
        out.loc[indices]=ranks*100
    return out

for metric in ['PE_Ratio','Price_to_Book','EV_to_EBITDA']:
    df[metric+'_valid']=df[metric].where(df[metric]>0)
for metric in ['PE_Ratio_valid','Price_to_Book_valid','EV_to_EBITDA_valid','Accruals','Asset_Growth','Debt_to_Assets']:
    df[metric+'_pct']=within_peer_percentile(df,metric,True)
df['ROA_pct']=within_peer_percentile(df,'ROA',False)
# Loss and negative cash-flow flags apply only if underlying values are observed.
df['Loss_Flag']=np.where(df['Net_Income'].notna(),np.where(df['Net_Income']<0,100.,0.),np.nan)
df['FCF_Flag']=np.where(df['Free_Cash_Flow'].notna(),np.where(df['Free_Cash_Flow']<0,100.,0.),np.nan)

def avg_with_min(frame,cols,min_count):
    vals=frame[cols]
    result=vals.mean(axis=1,skipna=True)
    return result.where(vals.notna().sum(axis=1)>=min_count)

df['Valuation_Score']=avg_with_min(df,['PE_Ratio_valid_pct','Price_to_Book_valid_pct','EV_to_EBITDA_valid_pct'],1)
df['Quality_Score']=avg_with_min(df,['Accruals_pct','FCF_Flag'],1)
df['Vulnerability_Score']=avg_with_min(df,['Asset_Growth_pct','Debt_to_Assets_pct','ROA_pct','Loss_Flag'],2)

components={'Valuation_Score':w_valuation,'Quality_Score':w_quality,'Vulnerability_Score':w_risk}
active={k:w for k,w in components.items() if w>0}
# Require ALL selected components; never silently redistribute missing component weights.
df['Eligible']=df[list(active)].notna().all(axis=1)
df['SELL_Risk_Score']=np.nan
if active:
    df.loc[df['Eligible'],'SELL_Risk_Score']=sum(df.loc[df['Eligible'],k]*w for k,w in active.items())/sum(active.values())

view=df[df['Industry'].isin(selected)&(df['Market_Cap']>=min_cap*1e6)].copy()
if require_valuation:
    view=view[view['Valuation_Score'].notna()]

c1,c2,c3,c4=st.columns(4)
c1.metric('Companies in universe',len(df))
c2.metric('Matching filters',len(view))
c3.metric('Fully scorable',int(view['Eligible'].sum()))
c4.metric('Historical records',len(hist))

st.subheader('Potential SELL-risk candidates')
st.caption('Higher scores mean more expensive relative valuation and/or greater financial vulnerability under the selected weights. Percentiles compare companies within Yahoo Finance industry classifications; groups need ≥5 valid peers per metric.')
scored=view[view['Eligible']].sort_values('SELL_Risk_Score',ascending=False)
cols=['Ticker','Company','Industry','Fiscal_End','SELL_Risk_Score','Valuation_Score','Quality_Score','Vulnerability_Score','PE_Ratio','Price_to_Book','EV_to_EBITDA','Accruals','ROA','Debt_to_Assets']

# Improve the appearance of the rankings table
table_display = scored[cols].copy()

table_display = table_display.rename(columns={
    "SELL_Risk_Score": "SELL Risk Score",
    "Valuation_Score": "Valuation Score",
    "Quality_Score": "Earnings Quality Score",
    "Vulnerability_Score": "Financial Vulnerability Score",
    "PE_Ratio": "P/E Ratio",
    "Price_to_Book": "Price to Book",
    "EV_to_EBITDA": "EV/EBITDA",
    "Debt_to_Assets": "Debt to Assets"
})


formats = {
    "SELL Risk Score": "{:.1f}",
    "Valuation Score": "{:.1f}",
    "Earnings Quality Score": "{:.1f}",
    "Financial Vulnerability Score": "{:.1f}",
    "P/E Ratio": "{:.2f}",
    "Price to Book": "{:.2f}",
    "EV/EBITDA": "{:.2f}",
    "Accruals": "{:.2%}",
    "ROA": "{:.2%}",
    "Debt to Assets": "{:.2%}"
}

formats = {
    col: fmt for col, fmt in formats.items()
    if col in table_display.columns
}
table_display["Fiscal_End"] = pd.to_datetime(table_display["Fiscal_End"], errors="coerce").dt.strftime("%Y-%m-%d")
st.dataframe(
    table_display.style.format(formats, na_rep="N/A"),
    use_container_width=True,
    hide_index=True
)


st.download_button('Download filtered rankings',data=scored[cols].to_csv(index=False).encode(),file_name='medivalue_rankings.csv',mime='text/csv')

st.subheader('Investigate a company')
options=sorted(view['Ticker'].dropna().tolist())
if options:
    ticker=st.selectbox('Company ticker',options,index=0)
    item=view[view['Ticker']==ticker].iloc[0]
    
   
    risk_score = item['SELL_Risk_Score']

    if pd.notna(risk_score):
        if risk_score >= 75:
            risk_label = "HIGH RISK"
            risk_title = "Elevated SELL Risk"
            risk_description = "Further investigation recommended."
            color = "#C94E0C"
            background = "#FFF3EA"
            border = "#FFD4B8"
        elif risk_score >= 40:
            risk_label = "MODERATE"
            risk_title = "Moderate SELL Risk"
            risk_description = "Mixed financial indicators."
            color = "#A66A00"
            background = "#FFF8E5"
            border = "#F4DEA4"
        else:
            risk_label = "LOWER RISK"
            risk_title = "Lower Relative SELL Risk"
            risk_description = "Fewer warning signals detected."
            color = "#087F83"
            background = "#EAF8F7"
            border = "#B5E2DF"
    else:
            risk_label = "NO SCORE"
            risk_title = "Insufficient Data"
            risk_description = "Risk score unavailable."
            color = "#64748B"
            background = "#F1F5F9"
            border = "#CBD5E1"

    st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:18px;
                background:{background};border:1px solid {border};
                border-radius:18px;padding:16px 20px;margin:16px 0;">
        <div style="border-radius:999px;background:{border};
                    color:{color};font-weight:800;text-align:center;
                    padding:17px 12px;min-width:92px;">
            {risk_label}
        </div>
        <div>
            <div style="font-size:21px;font-weight:700;color:{color};">
                {risk_title}
            </div>
            <div style="color:#475569;font-size:15px;">
                {risk_description}
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
    )
 
    st.markdown(f"**{item['Company']} ({ticker})** · {item['Industry']}")
    a,b,c,d=st.columns(4)
    a.metric('Combined SELL-risk score', f"{item['SELL_Risk_Score']:.1f}/100" if pd.notna(item['SELL_Risk_Score']) else 'Insufficient data')
    b.metric('Relative valuation', f"{item['Valuation_Score']:.1f}" if pd.notna(item['Valuation_Score']) else 'N/A')
    c.metric('Earnings quality risk', f"{item['Quality_Score']:.1f}" if pd.notna(item['Quality_Score']) else 'N/A')
    d.metric('Financial vulnerability', f"{item['Vulnerability_Score']:.1f}" if pd.notna(item['Vulnerability_Score']) else 'N/A')

    st.info(
            "How to interpret these scores: Higher scores indicate "
            "greater potential SELL risk, not a confirmed SELL recommendation. "
            "Relative Valuation measures how expensive a company appears "
            "compared with industry peers. Earnings Quality examines how "
            "well reported profits are supported by cash flow. Financial "
            "Vulnerability considers financial weaknesses such as debt "
            "and losses. Review the underlying financial data before "
            "drawing conclusions."
        )
    reasons=[]
    if pd.notna(item['Valuation_Score']) and item['Valuation_Score']>=75: reasons.append('High positive valuation multiples relative to industry peers')
    if pd.notna(item['Accruals']) and item['Accruals']>0: reasons.append('Net income exceeds operating cash flow relative to average assets')
    if pd.notna(item['Free_Cash_Flow']) and item['Free_Cash_Flow']<0: reasons.append('Negative free cash flow in the latest fiscal period')
    if pd.notna(item['Net_Income']) and item['Net_Income']<0: reasons.append('Reported net loss')
    if pd.notna(item['Debt_to_Assets']) and item['Debt_to_Assets']>.5: reasons.append('Debt exceeds half of reported assets')
    if reasons:
        st.markdown('**Signals to investigate:** '+ '; '.join(reasons)+'.')
    else:
        st.markdown('No predefined warning flags detected; review the underlying financial statements and peer context.')
        # Evidence-based short-candidate assessment
    if pd.notna(risk_score):
        if risk_score >= 75:
            st.warning(
                f"**Investment thesis — Potential SHORT candidate:** "
                f"{item['Company']} has a SELL-risk score of {risk_score:.1f}/100. "
                f"The model identifies elevated relative valuation, earnings-quality "
                f"and/or financial vulnerability concerns. "
                f"Key evidence: {('; '.join(reasons)) if reasons else 'elevated composite risk indicators'}. "
                f"This supports further short-side research, not an automatic trade."
            )
        elif risk_score >= 40:
            st.info(
                f"**Investment thesis — WATCHLIST:** "
                f"{item['Company']} scores {risk_score:.1f}/100, indicating "
                f"mixed valuation and financial-risk signals. "
                f"Further research is needed before forming a short thesis."
            )
        else:
            st.success(
                f"**Investment thesis — Lower relative short priority:** "
                f"{item['Company']} scores {risk_score:.1f}/100. "
                f"The model currently identifies fewer relative warning signals."
            )
    else:
        st.info(
            "**Investment thesis — Insufficient data:** "
            "The available financial information does not support a complete assessment."
        )
    h=hist[hist['Ticker']==ticker].sort_values('Fiscal_End').copy()
    if not h.empty:
        st.markdown('**Historical profitability and cash flow**')
        h=h.set_index('Fiscal_End')
        st.line_chart(h[['Net_Income','Operating_Cash_Flow','Free_Cash_Flow']].apply(pd.to_numeric,errors='coerce'))
        st.markdown('**Annual balance sheet and income statement**')

        historical_display = h.reset_index()[[
            'Fiscal_End', 'Revenue', 'Total_Assets', 'Total_Debt',
            'Net_Income', 'Operating_Cash_Flow', 'Accruals',
            'ROA', 'Asset_Growth'
        ]].copy()

        historical_display['Fiscal_End'] = pd.to_datetime(
            historical_display['Fiscal_End'], errors='coerce'
        ).dt.strftime('%Y-%m-%d')

        historical_display = historical_display.rename(columns={
            'Fiscal_End': 'Fiscal Year End',
            'Total_Assets': 'Total Assets',
            'Total_Debt': 'Total Debt',
            'Net_Income': 'Net Income',
            'Operating_Cash_Flow': 'Operating Cash Flow',
            'Asset_Growth': 'Asset Growth'
        })

        st.dataframe(
            historical_display.style.format({
                'Revenue': '{:,.0f}',
                'Total Assets': '{:,.0f}',
                'Total Debt': '{:,.0f}',
                'Net Income': '{:,.0f}',
                'Operating Cash Flow': '{:,.0f}',
                'Accruals': '{:.2%}',
                'ROA': '{:.2%}',
                'Asset Growth': '{:.2%}'
            }, na_rep='N/A'),
            use_container_width=True,
            hide_index=True
        )

st.subheader('Compare companies')
comparison=st.multiselect('Select up to 5 tickers',options,max_selections=5)
if comparison:

    comparison_display = view[view['Ticker'].isin(comparison)][['Ticker', 'Industry', 'SELL_Risk_Score', 'PE_Ratio', 'Price_to_Book', 'EV_to_EBITDA', 'Accruals', 'ROA', 'Debt_to_Assets', 'Free_Cash_Flow']].copy()
    comparison_display = comparison_display.replace(
        ["None", "nan", "NaN", ""], float("nan")
    )
    comparison_display = comparison_display.rename(columns={
        'SELL_Risk_Score': 'SELL Risk Score',
        'PE_Ratio': 'P/E Ratio',
        'Price_to_Book': 'Price to Book',
        'EV_to_EBITDA': 'EV/EBITDA',
        'Debt_to_Assets': 'Debt to Assets',
        'Free_Cash_Flow': 'Free Cash Flow'
    })

    st.dataframe(
        comparison_display.style.format({
            'SELL Risk Score': '{:.1f}',
            'P/E Ratio': '{:.2f}',
            'Price to Book': '{:.2f}',
            'EV/EBITDA': '{:.2f}',
            'Accruals': '{:.2%}',
            'ROA': '{:.2%}',
            'Debt to Assets': '{:.2%}',
            'Free Cash Flow': '{:,.0f}'
        }, na_rep='N/A'),
        use_container_width=True,
        hide_index=True
    )

with st.expander('Methodology, assumptions and limitations',expanded=False):
    st.markdown('''
**Connection to Quantitative Value:** MediValue is inspired by Gray and Carlisle's *Quantitative Value* approach, which emphasizes systematic, rules-based financial analysis to reduce behavioural bias in investment decisions. The screener combines relative valuation measures with earnings-quality and financial-vulnerability indicators to identify healthcare companies that warrant further investigation. Unlike the book's broader stock-selection framework, MediValue is designed specifically to screen for potential SELL-risk candidates rather than identify undervalued stocks to purchase. Its composite scores are original screening indicators, not the book's proprietary formulas or validated predictions of future stock performance.

**Sources:** Yahoo Finance via yfinance, using downloaded market snapshot and annual financial statement data. The data files are bundled with this app. The SEC was used for initial ticker discovery, not for validating every Yahoo accounting field.

**Financial ratios:** Accruals = (net income − operating cash flow) / average assets; ROA = net income / average assets; asset growth = assets / prior-year assets − 1; debt-to-assets = total debt / total assets; free cash flow = operating cash flow − absolute capital expenditures. Annual changes require fiscal dates roughly 330–400 days apart.

**Score:** For each metric, rank valid observations within the Yahoo industry peer group (at least five peers). Higher positive P/E, P/B and EV/EBITDA mean more expensive valuation. Negative or zero multiples are excluded from valuation scoring rather than interpreted as bargains. Quality combines accruals and negative-FCF flag. Vulnerability combines asset growth, debt/assets, inverse ROA, and loss flag. Component scores are averages of available signals, subject to minimum counts. The weighted composite uses the three sidebar weights and is only computed when every positively weighted component is available. Scores are relative screens, not calibrated probabilities of stock decline.

**Cautions:** Some companies have no meaningful P/E, no revenue, negative equity, or missing historical statements. Summary market fields and annual statement dates may not align; Yahoo Finance may restate or revise data. Subsector peers vary in business model, especially pre-revenue biotechnology. Industry percentile comparisons can be unstable for small groups. Stock valuation is not proof of overpricing, and SELL-risk flags are not investment recommendations. Before any real investment decision, verify filings, fiscal dates, share classes, and current market prices.
''')
    st.write('Market-data fields present:', ', '.join(pd.read_csv(BASE/'medivalue_market_data.csv',nrows=0).columns))

