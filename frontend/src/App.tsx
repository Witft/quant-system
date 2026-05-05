// @ts-nocheck
import { useEffect, useState } from 'react';
import axios from 'axios';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, ScatterChart, Scatter, ZAxis } from 'recharts';
import { Activity, ShieldAlert, TrendingUp, BarChart2 } from 'lucide-react';

const API_BASE = 'http://47.97.98.164:8000/api';

export default function App() {
  const [stats, setStats] = useState<any>({});
  const [picks, setPicks] = useState<any[]>([]);

  useEffect(() => {
    axios.get(`${API_BASE}/stats`).then(res => setStats(res.data)).catch(console.error);
    axios.get(`${API_BASE}/picks`).then(res => setPicks(res.data?.data || res.data || [])).catch(console.error);
  }, []);

  const getMarginColor = (margin: any) => {
    if (margin == null) return "bg-slate-300";
    if (margin > 60) return "bg-green-500";
    if (margin > 40) return "bg-blue-500";
    return "bg-amber-500";
  };

  // Process data for Margin Bar Chart safely
  const marginData = picks.slice(0, 10).map(p => ({
    name: p.code,
    margin: p.margin || 0,
    price: p.price || 0,
    value: p.graham || 0
  }));

  // Process data for ROE vs Debt Scatter safely
  const scatterData = picks.map(p => ({
    name: p.code,
    x: p.roe || 0,
    y: p.debt_to_assets || 0,
    z: p.margin || 50
  }));

  const formatNum = (val: any, decimals: number = 2) => {
    if (val == null || isNaN(val)) return '-';
    return Number(val).toFixed(decimals);
  };

  return (
    <div className="min-h-screen bg-slate-50 p-8">
      <div className="max-w-7xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold text-slate-900 tracking-tight">量化推荐看板</h1>
          <p className="text-slate-500 mt-2">A股价值投资每日扫盘分析</p>
        </div>

        {/* Stats Row */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-slate-500">累计运行天数</CardTitle>
              <Activity className="h-4 w-4 text-slate-400" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_days || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-slate-500">总推荐标的</CardTitle>
              <BarChart2 className="h-4 w-4 text-slate-400" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stats.total_picks || 0}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-slate-500">平均安全边际</CardTitle>
              <ShieldAlert className="h-4 w-4 text-slate-400" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatNum(stats.avg_margin)}%</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium text-slate-500">平均 ROE</CardTitle>
              <TrendingUp className="h-4 w-4 text-slate-400" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{formatNum(stats.avg_roe)}%</div>
            </CardContent>
          </Card>
        </div>

        {/* Charts Row */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <Card>
            <CardHeader>
              <CardTitle>Top 10 安全边际</CardTitle>
            </CardHeader>
            <CardContent className="h-[350px] min-h-[350px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={marginData} margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="name" fontSize={12} tickMargin={10} />
                  <YAxis fontSize={12} tickFormatter={(val) => `${val}%`} />
                  <RechartsTooltip />
                  <Bar dataKey="margin" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>ROE vs 负债率 (避开价值陷阱)</CardTitle>
            </CardHeader>
            <CardContent className="h-[350px] min-h-[350px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ScatterChart margin={{ top: 20, right: 30, left: 0, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" dataKey="x" name="ROE" unit="%" fontSize={12} />
                  <YAxis type="number" dataKey="y" name="负债率" unit="%" fontSize={12} />
                  <ZAxis type="number" dataKey="z" range={[50, 400]} name="安全边际" />
                  <RechartsTooltip cursor={{ strokeDasharray: '3 3' }} />
                  <Scatter name="Picks" data={scatterData} fill="#8b5cf6" />
                </ScatterChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </div>

        {/* Table */}
        <Card>
          <CardHeader>
            <CardTitle>最新推荐名单</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>日期</TableHead>
                  <TableHead>代码</TableHead>
                  <TableHead>现价</TableHead>
                  <TableHead>内在价值</TableHead>
                  <TableHead>安全边际</TableHead>
                  <TableHead>PE / PB</TableHead>
                  <TableHead>建议</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {picks.map((pick, i) => (
                  <TableRow key={i}>
                    <TableCell className="font-mono text-xs text-slate-500">{pick.trade_date}</TableCell>
                    <TableCell className="font-semibold">{pick.code}</TableCell>
                    <TableCell>¥{formatNum(pick.price)}</TableCell>
                    <TableCell>¥{formatNum(pick.graham)}</TableCell>
                    <TableCell>
                      <Badge className={`${getMarginColor(pick.margin)} border-none text-white`}>
                        {formatNum(pick.margin, 1)}%
                      </Badge>
                    </TableCell>
                    <TableCell className="text-slate-600 text-sm">
                      {formatNum(pick.pe, 1)} / {formatNum(pick.pb)}
                    </TableCell>
                    <TableCell className="text-sm truncate max-w-xs" title={pick.reasoning || ""}>
                      {(pick.reasoning || "").substring(0, 30)}...
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
