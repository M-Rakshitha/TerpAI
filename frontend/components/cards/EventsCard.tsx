'use client';

import React from 'react';
import { EventsResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface EventsCardProps {
  data: EventsResult;
}

const EventsCard: React.FC<EventsCardProps> = ({ data }) => {
  const { events } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Upcoming Events</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {events.map((event, index) => (
          <div key={index} className="p-3 border rounded-lg">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{event.title}</h3>
              {event.free_food && <Badge variant="secondary">Free Food</Badge>}
            </div>
            <p className="text-sm text-gray-600">{event.location}</p>
            <p className="text-sm text-gray-500">{new Date(event.start).toLocaleString()}</p>
            <div className="flex gap-1 mt-2">
              {event.tags.map((tag, tagIndex) => (
                <Badge key={tagIndex} variant="outline" className="text-xs">
                  {tag}
                </Badge>
              ))}
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
};

export default EventsCard;