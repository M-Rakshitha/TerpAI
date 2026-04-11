'use client';

import React from 'react';
import { DiningResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface DiningCardProps {
  data: DiningResult;
}

const DiningCard: React.FC<DiningCardProps> = ({ data }) => {
  const { options } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Dining Options</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {options.map((option, index) => (
          <div key={index} className="flex items-center justify-between p-3 border rounded-lg">
            <div>
              <p className="font-semibold">{option.name}</p>
              <p className="text-sm text-gray-600">{option.distance_min} min walk</p>
              <div className="flex gap-1 mt-1">
                {option.dietary_tags.map((tag, tagIndex) => (
                  <Badge key={tagIndex} variant="secondary" className="text-xs">
                    {tag}
                  </Badge>
                ))}
              </div>
            </div>
            <div className="text-right">
              <Badge variant={option.budget_ok ? 'default' : 'destructive'}>
                {option.budget_ok ? 'Budget OK' : 'Over Budget'}
              </Badge>
              <p className="text-xs text-gray-500 mt-1">
                {option.hours_open ? 'Open' : 'Closed'}
              </p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default DiningCard;