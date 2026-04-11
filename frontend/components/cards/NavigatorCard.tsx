'use client';

import React from 'react';
import { NavigatorResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface NavigatorCardProps {
  data: NavigatorResult;
}

const NavigatorCard: React.FC<NavigatorCardProps> = ({ data }) => {
  const { origin, destination, walk_minutes, steps, map_url } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Navigation</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600">From: {origin}</p>
            <p className="text-sm text-gray-600">To: {destination}</p>
          </div>
          <p className="font-semibold">{walk_minutes} min walk</p>
        </div>
        <div className="space-y-1">
          {steps.map((step, index) => (
            <p key={index} className="text-sm">{index + 1}. {step}</p>
          ))}
        </div>
        <Button className="w-full" onClick={() => window.open(map_url, '_blank')}>
          Open in Maps
        </Button>
      </CardContent>
    </Card>
  );
};

export default NavigatorCard;