import React from 'react';
import { DiningResult } from '@/lib/types';
import { Card, Badge } from '@/components/ui'; // Assuming ShadCN components are in the ui folder

interface DiningCardProps {
  data: DiningResult;
}

const DiningCard: React.FC<DiningCardProps> = ({ data }) => {
  return (
    <Card>
      <h2 className="text-lg font-semibold">Dining Options</h2>
      <ul className="space-y-4">
        {data.options.map((option, index) => (
          <li key={index} className="flex justify-between items-center">
            <div>
              <h3 className="text-md font-medium">{option.name}</h3>
              <div className="flex items-center space-x-2">
                <span className={`text-sm ${option.budget_ok ? 'text-green-500' : 'text-red-500'}`}>
                  {option.budget_ok ? '✔️ Budget OK' : '❌ Budget Exceeded'}
                </span>
                <span className={`text-sm ${option.hours_open ? 'text-green-500' : 'text-red-500'}`}>
                  {option.hours_open ? '🕒 Open' : '🚫 Closed'}
                </span>
                {option.dietary_tags.map((tag, tagIndex) => (
                  <Badge key={tagIndex} className="text-xs">{tag}</Badge>
                ))}
              </div>
              <span className="text-sm text-gray-500">{option.distance_min} min walk</span>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
};

export default DiningCard;