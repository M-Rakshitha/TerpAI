import React, { useState } from 'react';
import { QueryResponse } from '@/lib/types';
import { Card, Tabs, Tab, Button } from '@/components/ui'; // Assuming ShadCN components are used

const JobsResearchCard: React.FC<{ data: QueryResponse['results']['jobs_research'] }> = ({ data }) => {
  const [activeTab, setActiveTab] = useState<'jobs' | 'labs'>('jobs');

  return (
    <Card>
      <Tabs activeTab={activeTab} onChange={setActiveTab}>
        <Tab value="jobs">Campus Jobs</Tab>
        <Tab value="labs">Research Labs</Tab>
      </Tabs>
      {activeTab === 'jobs' && (
        <div>
          {data.jobs.length > 0 ? (
            data.jobs.map((job, index) => (
              <div key={index} className="flex justify-between p-4 border-b">
                <div>
                  <h3 className="font-bold">{job.title}</h3>
                  <p>{job.department}</p>
                  <p>{job.pay}</p>
                </div>
              </div>
            ))
          ) : (
            <p>No campus jobs available.</p>
          )}
        </div>
      )}
      {activeTab === 'labs' && (
        <div>
          {data.labs.length > 0 ? (
            data.labs.map((lab, index) => (
              <div key={index} className="flex justify-between p-4 border-b">
                <div>
                  <h3 className="font-bold">{lab.pi}</h3>
                  <p>{lab.topic}</p>
                  <p>Contact: {lab.contact}</p>
                </div>
              </div>
            ))
          ) : (
            <p>No research labs available.</p>
          )}
          {data.cold_email && (
            <div className="mt-4">
              <Button onClick={() => navigator.clipboard.writeText(data.cold_email)}>
                Copy email draft
              </Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
};

export default JobsResearchCard;