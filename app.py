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
st.caption('Higher scores reflect relatively expensive **valid positive** valuation multiples and/or financial risk. A high score is a research flag, not proof that a stock is overpriced.')
scored=view[view['Eligible']].sort_values('SELL_Risk_Score',ascending=False)
cols=['Ticker','Company','Industry','Fiscal_End_Display','SELL_Risk_Score','Valuation_Score','Quality_Score','Vulnerability_Score','PE_Ratio','Price_to_Book','EV_to_EBITDA','Accruals','ROA','Debt_to_Assets']
labels={'Fiscal_End_Display':'Fiscal End','SELL_Risk_Score':'SELL Risk Score','Valuation_Score':'Valuation Score','Quality_Score':'Earnings Quality Score','Vulnerability_Score':'Financial Vulnerability Score','PE_Ratio':'P/E Ratio','Price_to_Book':'Price to Book','EV_to_EBITDA':'EV/EBITDA','Debt_to_Assets':'Debt to Assets'}
table_display=scored[cols].rename(columns=labels)
format_columns={
    'SELL Risk Score':st.column_config.NumberColumn(format='%.1f'),
    'Valuation Score':st.column_config.NumberColumn(format='%.1f'),
    'Earnings Quality Score':st.column_config.NumberColumn(format='%.1f'),
    'Financial Vulnerability Score':st.column_config.NumberColumn(format='%.1f'),
    'P/E Ratio':st.column_config.NumberColumn(format='%.2f'),
    'Price to Book':st.column_config.NumberColumn(format='%.2f'),
    'EV/EBITDA':st.column_config.NumberColumn(format='%.2f'),
    'Accruals':st.column_config.NumberColumn(format='%.2f%%'),
    'ROA':st.column_config.NumberColumn(format='%.2f%%'),
    'Debt to Assets':st.column_config.NumberColumn(format='%.2f%%'),
}
# Percentages are converted to percent units for display only.
for percent_col in ['Accruals','ROA','Debt to Assets']:
    table_display[percent_col]=table_display[percent_col]*100
st.dataframe(table_display,hide_index=True,use_container_width=True,column_config=format_columns)
st.download_button('Download filtered rankings',data=scored[cols].rename(columns={'Fiscal_End_Display':'Fiscal_End'}).to_csv(index=False).encode(),file_name='medivalue_rankings.csv',mime='text/csv')
with st.expander('How to interpret the rankings'):
    st.markdown("""**Valuation:** Positive P/E, price-to-book and EV/EBITDA multiples are compared within industry peer groups. Nonpositive multiples are not treated as cheap.  
**Earnings quality:** Accruals and negative free cash flow provide signals about cash support for reported results.  
**Financial vulnerability:** Asset growth, leverage, low ROA and losses contribute to the risk screen.  
**Missing data:** Companies without all components required by your chosen positive weights do not receive a composite score. Rankings are relative, not predictions of returns.""")

st.subheader('Investigate a company')
options=sorted(view['Ticker'].dropna().tolist())
if options:
    ticker=st.selectbox('Company ticker',options,index=0)
    item=view[view['Ticker']==ticker].iloc[0]
    st.markdown(f"**{item['Company']} ({ticker})** · {item['Industry']}")
    a,b,c=st.columns(3)
    a.metric('Combined SELL-risk score',f"{item['SELL_Risk_Score']:.1f}/100" if pd.notna(item['SELL_Risk_Score']) else 'Insufficient data')
    b.metric('Relative valuation score',f"{item['Valuation_Score']:.1f}" if pd.notna(item['Valuation_Score']) else 'N/A')
    c.metric('Financial vulnerability',f"{item['Vulnerability_Score']:.1f}" if pd.notna(item['Vulnerability_Score']) else 'N/A')
    st.caption('Scores are industry-relative risk signals (0–100), not probabilities of a price decline.')
    if pd.isna(item['Valuation_Score']):
        st.warning('Insufficient valid positive valuation multiples or industry peers for a valuation score. Financial weakness alone does not establish overvaluation.')
    else:
        st.write(f"Valuation score: **{item['Valuation_Score']:.1f}/100** relative to eligible industry peers. Review the underlying multiples before drawing conclusions.")
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
    h=hist[hist['Ticker']==ticker].sort_values('Fiscal_End').copy()
    if not h.empty:
        st.markdown('**Historical profitability and cash flow**')
        h=h.set_index('Fiscal_End')
        st.line_chart(h[['Net_Income','Operating_Cash_Flow','Free_Cash_Flow']].apply(pd.to_numeric,errors='coerce'))
        st.markdown('**Annual balance sheet and income statement**')
        st.dataframe(h[['Revenue','Total_Assets','Total_Debt','Net_Income','Operating_Cash_Flow','Accruals','ROA','Asset_Growth']].sort_index(ascending=False),use_container_width=True)

st.subheader('Compare companies')
comparison=st.multiselect('Select up to 5 tickers',options,max_selections=5)
if comparison:
    compare_cols=['Ticker','Company','Industry','SELL_Risk_Score','Valuation_Score','Quality_Score','Vulnerability_Score','PE_Ratio','Price_to_Book','EV_to_EBITDA','Accruals','ROA','Debt_to_Assets','Free_Cash_Flow']
    comp=view[view['Ticker'].isin(comparison)][compare_cols].copy()
    st.dataframe(comp,hide_index=True,use_container_width=True,column_config={
        'SELL_Risk_Score':st.column_config.NumberColumn('SELL Risk Score',format='%.1f'),
        'Valuation_Score':st.column_config.NumberColumn('Valuation Score',format='%.1f'),
        'Quality_Score':st.column_config.NumberColumn('Quality Score',format='%.1f'),
        'Vulnerability_Score':st.column_config.NumberColumn('Vulnerability Score',format='%.1f'),
    })
    st.markdown('**Compare historical performance**')
    metric=st.selectbox('Financial indicator',['ROA','Accruals','Debt_to_Assets','Asset_Growth','Operating_Cash_Flow','Net_Income','Free_Cash_Flow','Revenue'],index=0)
    plot=hist[hist['Ticker'].isin(comparison)][['Ticker','Fiscal_End',metric]].copy()
    plot[metric]=pd.to_numeric(plot[metric],errors='coerce')
    plot=plot.dropna(subset=['Fiscal_End',metric])
    if plot.empty:
        st.info('No historical observations available for the selected metric and companies.')
    else:
        chart=plot.pivot_table(index='Fiscal_End',columns='Ticker',values=metric,aggfunc='last').sort_index()
        st.line_chart(chart,use_container_width=True)
        st.caption('Annual fiscal-end observations; reporting dates may differ across companies. Monetary amounts are in reported currency units, typically USD.')

with st.expander('Methodology, assumptions and limitations',expanded=False):
    st.markdown('''
**Sources:** Yahoo Finance via yfinance, using downloaded market snapshot and annual financial statement data. The data files are bundled with this app. The SEC was used for initial ticker discovery, not for validating every Yahoo accounting field.

**Financial ratios:** Accruals = (net income − operating cash flow) / average assets; ROA = net income / average assets; asset growth = assets / prior-year assets − 1; debt-to-assets = total debt / total assets; free cash flow = operating cash flow − absolute capital expenditures. Annual changes require fiscal dates roughly 330–400 days apart.

**Weighted score:** SELL-risk score = (valuation weight × valuation score + earnings-quality weight × quality score + vulnerability weight × vulnerability score) / sum of active weights. The default weights are 40, 35 and 25. Moving sliders recalculates the ranking immediately.

**Score:** For each metric, rank valid observations within the Yahoo industry peer group (at least five peers). Higher positive P/E, P/B and EV/EBITDA mean more expensive valuation. Negative or zero multiples are excluded from valuation scoring rather than interpreted as bargains. Quality combines accruals and negative-FCF flag. Vulnerability combines asset growth, debt/assets, inverse ROA, and loss flag. Component scores are averages of available signals, subject to minimum counts. The weighted composite uses the three sidebar weights and is only computed when every positively weighted component is available. Scores are relative screens, not calibrated probabilities of stock decline.

**Cautions:** Some companies have no meaningful P/E, no revenue, negative equity, or missing historical statements. Summary market fields and annual statement dates may not align; Yahoo Finance may restate or revise data. Subsector peers vary in business model, especially pre-revenue biotechnology. Industry percentile comparisons can be unstable for small groups. Stock valuation is not proof of overpricing, and SELL-risk flags are not investment recommendations. Before any real investment decision, verify filings, fiscal dates, share classes, and current market prices.
''')
    st.write('Market-data fields present:', ', '.join(pd.read_csv(BASE/'medivalue_market_data.csv',nrows=0).columns))
