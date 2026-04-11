'use client';

import React from 'react';
import { ScheduleResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { formatDistanceToNow } from 'date-fns';

interface ScheduleCardProps {
  data: ScheduleResult;
}

const ScheduleCard: React.FC<ScheduleCardProps> = ({ data }) => {
  const { study_blocks, next_deadline } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upcoming Schedule</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {next_deadline && (
          <div className="p-3 bg-blue-50 rounded-lg">
            <p className="font-semibold">{next_deadline.title}</p>
            <p className="text-sm text-gray-600">
              {`Due in ${formatDistanceToNow(new Date(next_deadline.due), {
                addSuffix: true,
              })}`}
            </p>
          </div>
        )}
        <div className="space-y-2">
          {study_blocks.map((block, index) => (
            <div key={index} className="flex items-center justify-between p-2 border-l-4" style={{
              borderLeftColor: block.type === 'review' ? '#3b82f6' : block.type === 'practice' ? '#f59e0b' : '#9ca3af'
            }}>
              <span className="font-medium">{block.subject}</span>
              <span className="text-sm text-gray-600">{`${block.start} - ${block.end}`}</span>
              <span className="text-xs font-semibold capitalize" style={{
                color: block.type === 'review' ? '#3b82f6' : block.type === 'practice' ? '#f59e0b' : '#9ca3af'
              }}>
                {block.type}
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
};

export default ScheduleCard;