'use client';

import React, { useState } from 'react';
import { JobsResearchResult } from '@/lib/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';

interface JobsResearchCardProps {
  data: JobsResearchResult;
}

const JobsResearchCard: React.FC<JobsResearchCardProps> = ({ data }) => {
  const [copiedEmail, setCopiedEmail] = useState(false);

  const handleCopyEmail = () => {
    navigator.clipboard.writeText(data.cold_email);
    setCopiedEmail(true);
    setTimeout(() => setCopiedEmail(false), 2000);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Jobs & Research</CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="jobs" className="w-full">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="jobs">Jobs</TabsTrigger>
            <TabsTrigger value="labs">Labs</TabsTrigger>
            <TabsTrigger value="email">Email</TabsTrigger>
          </TabsList>
          
          <TabsContent value="jobs" className="space-y-2">
            {data.jobs?.map((job, index) => (
              <div key={index} className="p-3 border rounded-lg">
                <p className="font-semibold">{job.title}</p>
                <p className="text-sm text-gray-600">{job.department}</p>
                <p className="text-sm font-medium text-green-600">{job.pay}</p>
                <Button className="mt-2 w-full" size="sm" onClick={() => window.open(job.apply_url, '_blank')}>
                  Apply
                </Button>
              </div>
            ))}
          </TabsContent>

          <TabsContent value="labs" className="space-y-2">
            {data.labs?.map((lab, index) => (
              <div key={index} className="p-3 border rounded-lg">
                <p className="font-semibold">{lab.pi}</p>
                <p className="text-sm text-gray-600">{lab.topic}</p>
                <p className="text-xs text-gray-500">{lab.department}</p>
                <p className="text-xs text-gray-400">{lab.contact}</p>
              </div>
            ))}
          </TabsContent>

          <TabsContent value="email" className="space-y-3">
            <div className="p-3 bg-gray-50 rounded-lg max-h-40 overflow-y-auto">
              <p className="text-sm whitespace-pre-wrap">{data.cold_email}</p>
            </div>
            <Button onClick={handleCopyEmail} className="w-full">
              {copiedEmail ? 'Copied!' : 'Copy Email'}
            </Button>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
};

export default JobsResearchCard;