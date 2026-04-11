import React from 'react';
import { EventsResult } from '@/lib/types';
import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';

interface EventsCardProps {
  eventsData: EventsResult | null;
}

const EventsCard: React.FC<EventsCardProps> = ({ eventsData }) => {
  if (!eventsData || eventsData.events.length === 0) {
    return null; // Don't render if no events
  }

  return (
    <Card>
      <h2 className="text-lg font-semibold">Upcoming Events</h2>
      <ul className="mt-4 space-y-2">
        {eventsData.events.map((event, index) => (
          <li key={index} className="flex justify-between items-center p-4 border-b">
            <div>
              <h3 className="font-medium">{event.title}</h3>
              <p className="text-sm text-gray-500">{event.location}</p>
              <p className="text-sm text-gray-400">{new Date(event.start).toLocaleString()}</p>
            </div>
            {event.free_food && <Badge color="green">Free Food</Badge>}
            <div className="flex space-x-2">
              {event.tags.map((tag, tagIndex) => (
                <Badge key={tagIndex} color="blue">{tag}</Badge>
              ))}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
};

export default EventsCard;