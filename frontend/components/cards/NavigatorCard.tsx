import React from 'react';
import { GoogleMap, Marker } from '@react-google-maps/api';
import { Card } from '@/components/ui/Card';
import { NavigatorResult } from '@/lib/types';

interface NavigatorCardProps {
  data: NavigatorResult;
}

const NavigatorCard: React.FC<NavigatorCardProps> = ({ data }) => {
  return (
    <Card>
      <h2 className="text-lg font-semibold">Navigation Details</h2>
      <p className="text-xl">{data.walk_minutes} min walk</p>
      <GoogleMap
        mapContainerStyle={{ height: '400px', width: '100%' }}
        center={{ lat: 0, lng: 0 }} // Replace with actual coordinates
        zoom={15}
      >
        <Marker position={{ lat: 0, lng: 0 }} /> {/* Replace with actual coordinates */}
      </GoogleMap>
      <ol className="mt-4">
        {data.steps.map((step, index) => (
          <li key={index}>{step}</li>
        ))}
      </ol>
    </Card>
  );
};

export default NavigatorCard;