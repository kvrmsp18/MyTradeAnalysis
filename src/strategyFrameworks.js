const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const first = (obj, keys) => {
  for (const key of keys) {
    const value = num(obj?.[key]);
    if (value !== null) return value;
  }
  return null;
};

function evaluate(symbol, data) {
  const s = data || {};
  const checks = [];
  const add = (name, value, passWhen) => {
    if (value === null) checks.push({ name, state: 'UNAVAILABLE' });
    else checks.push({ name, state: passWhen(value) ? 'PASS' : 'REVIEW' });
  };

  // Warren Buffett: quality, returns on capital, cash generation and balance-sheet quality.
  add('ROIC / ROCE', first(s, ['roic','roce']), v => v >= 15);
  add('Free cash flow', first(s, ['free_cash_flow','fcf']), v => v > 0);
  add('Debt discipline', first(s, ['debt_to_equity','debt_equity']), v => v <= 1);
  const buffett = checks.slice();

  // Rakesh Jhunjhunwala: earnings growth, sector tailwind and operating leverage.
  checks.length = 0;
  add('Earnings growth', first(s, ['earnings_growth','profit_growth','eps_growth']), v => v >= 15);
  add('Revenue growth', first(s, ['revenue_growth','sales_growth']), v => v >= 10);
  add('Sector growth', first(s, ['sector_growth','sector_tailwind']), v => v >= 10);
  add('Operating leverage', first(s, ['operating_leverage']), v => v > 0);
  const jhunjhunwala = checks.slice();

  // Peter Lynch: growth relative to valuation and understandable growth characteristics.
  checks.length = 0;
  add('PEG', first(s, ['peg','peg_ratio']), v => v > 0 && v <= 1.5);
  add('Earnings growth', first(s, ['earnings_growth','profit_growth','eps_growth']), v => v >= 10);
  add('P/E', first(s, ['pe','pe_ratio']), v => v > 0 && v <= 35);
  const lynch = checks.slice();

  // 100 Baggers: high returns on capital, reinvestment and long runway.
  checks.length = 0;
  add('ROIC / ROCE', first(s, ['roic','roce']), v => v >= 15);
  add('Reinvestment rate', first(s, ['reinvestment_rate']), v => v >= 10);
  add('Growth runway', first(s, ['runway_years']), v => v >= 5);
  add('Revenue growth', first(s, ['revenue_growth','sales_growth']), v => v >= 10);
  const hundred = checks.slice();

  // CANSLIM / William O'Neil: earnings acceleration plus price/volume leadership.
  checks.length = 0;
  add('EPS growth', first(s, ['eps_growth','earnings_growth']), v => v >= 20);
  add('Sales growth', first(s, ['sales_growth','revenue_growth']), v => v >= 10);
  add('Price momentum', first(s, ['price_change_20d','change_20d','change']), v => v > 0);
  add('Relative strength', first(s, ['relative_strength','rs_rating']), v => v >= 70);
  add('Volume confirmation', first(s, ['volume_ratio','volume_vs_average']), v => v >= 1.2);
  const canslim = checks.slice();

  const groups = [
    { id:'buffett', name:'Warren Buffett', focus:'Quality, moat, capital preservation', checks:buffett },
    { id:'jhunjhunwala', name:'Jhunjhunwala', focus:'Secular growth, earnings and leverage', checks:jhunjhunwala },
    { id:'lynch', name:'Peter Lynch', focus:'Growth versus valuation', checks:lynch },
    { id:'hundred_baggers', name:'100 Baggers', focus:'Reinvestment and long runway', checks:hundred },
    { id:'canslim', name:"CANSLIM / O'Neil", focus:'Growth, momentum and leadership', checks:canslim }
  ];

  return groups.map(group => {
    const available = group.checks.filter(c => c.state !== 'UNAVAILABLE').length;
    const passed = group.checks.filter(c => c.state === 'PASS').length;
    return {
      ...group,
      status: available === 0 ? 'UNAVAILABLE' : available < group.checks.length ? 'PARTIAL' : (passed >= Math.ceil(group.checks.length * 0.6) ? 'PASS' : 'REVIEW'),
      available,
      passed,
      evidenceCompleteness: Math.round((available / group.checks.length) * 100)
    };
  });
}

export function evaluateFrameworks(stock) {
  return evaluate(stock?.symbol || 'UNKNOWN', stock);
}

export function frameworkSummary(stock) {
  return evaluateFrameworks(stock).map(item => ({
    id: item.id,
    name: item.name,
    focus: item.focus,
    status: item.status,
    passed: item.passed,
    available: item.available,
    total: item.checks.length,
    evidenceCompleteness: item.evidenceCompleteness
  }));
}
