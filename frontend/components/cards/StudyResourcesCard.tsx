'use client';

import React from 'react';
import { StudyResourcesResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface StudyResourcesCardProps {
  data: StudyResourcesResult;
}

const StudyResourcesCard: React.FC<StudyResourcesCardProps> = ({ data }) => {
  const { tutoring, office_hours } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Study Resources</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="tutoring" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="tutoring">Tutoring</TabsTrigger>
            <TabsTrigger value="office-hours">Office Hours</TabsTrigger>
          </TabsList>
          
          <TabsContent value="tutoring" className="space-y-2">
            {tutoring.map((item, index) => (
              <div key={index} className="p-3 border rounded-lg">
                <p className="font-semibold">{item.service}</p>
                <p className="text-sm text-gray-600">{item.subject}</p>
                <p className="text-sm text-gray-500">{item.schedule}</p>
                <p className="text-xs text-gray-400">{item.location}</p>
              </div>
            ))}
          </TabsContent>

          <TabsContent value="office-hours" className="space-y-2">
            {office_hours.map((item, index) => (
              <div key={index} className="p-3 border rounded-lg">
                <p className="font-semibold">{item.professor}</p>
                <p className="text-sm text-gray-600">{item.course}</p>
                <p className="text-sm text-gray-500">{item.time}</p>
                <p className="text-xs text-gray-400">{item.room}</p>
              </div>
            ))}
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};

export default StudyResourcesCard;