import React from 'react';
import { ScheduleResult } from '@/lib/types';
import { Card } from '@/components/ui/Card';
import { formatDistanceToNow } from 'date-fns';

interface ScheduleCardProps {
  data: ScheduleResult;
}

const ScheduleCard: React.FC<ScheduleCardProps> = ({ data }) => {
  const { study_blocks, next_deadline } = data;

  return (
    <Card>
      <h2 className="text-lg font-bold">Upcoming Schedule</h2>
      {next_deadline && (
        <div className="mb-4">
          <p>Next deadline: {next_deadline.title}</p>
          <p>
            {`Due in ${formatDistanceToNow(new Date(next_deadline.due), {
              addSuffix: true,
            })}`}
          </p>
        </div>
      )}
      <div className="flex flex-col">
        {study_blocks.map((block, index) => (
          <div key={index} className="flex items-center justify-between">
            <span>{block.subject}</span>
            <span>{`${block.start} - ${block.end}`}</span>
            <span
              className={`ml-2 ${
                block.type === 'review'
                  ? 'text-blue-500'
                  : block.type === 'practice'
                  ? 'text-amber-500'
                  : 'text-gray-500'
              }`}
            >
              {block.type}
            </span>
          </div>
        ))}
      </div>
    </Card>
  );
};

export default ScheduleCard;