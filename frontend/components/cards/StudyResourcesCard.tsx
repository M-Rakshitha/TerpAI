import React from 'react';
import { QueryResponse } from '@/lib/types';
import { Card } from '@/components/ui/Card';

interface StudyResourcesCardProps {
  data: QueryResponse['results']['study_resources'];
}

const StudyResourcesCard: React.FC<StudyResourcesCardProps> = ({ data }) => {
  if (!data) return null;

  return (
    <Card>
      <h2 className="text-lg font-semibold">Tutoring</h2>
      {data.tutoring.length > 0 ? (
        <ul>
          {data.tutoring.map((tutor, index) => (
            <li key={index} className="py-2">
              <strong>{tutor.service}</strong> - {tutor.subject} ({tutor.schedule}) at {tutor.location}
            </li>
          ))}
        </ul>
      ) : (
        <p>No tutoring resources available.</p>
      )}

      <h2 className="text-lg font-semibold mt-4">Office Hours</h2>
      {data.office_hours.length > 0 ? (
        <ul>
          {data.office_hours.map((officeHour, index) => (
            <li key={index} className="py-2">
              <strong>{officeHour.professor}</strong> - {officeHour.course} ({officeHour.time}) in {officeHour.room}
            </li>
          ))}
        </ul>
      ) : (
        <p>No office hours available.</p>
      )}
    </Card>
  );
};

export default StudyResourcesCard;