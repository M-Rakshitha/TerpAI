import React from 'react';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import { FinanceResult } from '@/lib/types';

interface FinanceCardProps {
  data: FinanceResult;
}

const FinanceCard: React.FC<FinanceCardProps> = ({ data }) => {
  const { weekly_spent, budget_remaining, suggestion } = data;

  const chartData = [
    { name: 'Spent', value: weekly_spent },
    { name: 'Remaining', value: budget_remaining },
  ];

  const COLORS = ['#0088FE', '#00C49F'];

  return (
    <div className="p-4 bg-white rounded-lg shadow-md">
      <h2 className="text-lg font-semibold">Finance Overview</h2>
      <PieChart width={400} height={200}>
        <Pie
          data={chartData}
          cx={200}
          cy={100}
          innerRadius={40}
          outerRadius={80}
          fill="#8884d8"
          paddingAngle={5}
          dataKey="value"
        >
          {chartData.map((entry, index) => (
            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
          ))}
        </Pie>
        <Tooltip />
      </PieChart>
      <p className="mt-4 italic">"{suggestion}"</p>
    </div>
  );
};

export default FinanceCard;