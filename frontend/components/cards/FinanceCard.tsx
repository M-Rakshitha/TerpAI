'use client';

import React from 'react';
import { PieChart, Pie, Cell, Tooltip } from 'recharts';
import { FinanceResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

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
    <Card>
      <CardHeader>
        <CardTitle>Finance Overview</CardTitle>
      </CardHeader>
      <CardContent>
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
      </CardContent>
    </Card>
  );
};

export default FinanceCard;