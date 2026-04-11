'use client';

import React from 'react';
import { QueryResponse } from '@/lib/types';
import ScheduleCard from '@/components/cards/ScheduleCard';
import DiningCard from '@/components/cards/DiningCard';
import EventsCard from '@/components/cards/EventsCard';
import FinanceCard from '@/components/cards/FinanceCard';
import NavigatorCard from '@/components/cards/NavigatorCard';
import StudyResourcesCard from '@/components/cards/StudyResourcesCard';
import JobsResearchCard from '@/components/cards/JobsResearchCard';

interface DashboardProps {
  data: QueryResponse;
}

const Dashboard: React.FC<DashboardProps> = ({ data }) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      {data.results.schedule && <ScheduleCard data={data.results.schedule} />}
      {data.results.dining && <DiningCard data={data.results.dining} />}
      {data.results.events && <EventsCard data={data.results.events} />}
      {data.results.finance && <FinanceCard data={data.results.finance} />}
      {data.results.navigator && <NavigatorCard data={data.results.navigator} />}
      {data.results.study_resources && <StudyResourcesCard data={data.results.study_resources} />}
      {data.results.jobs_research && <JobsResearchCard data={data.results.jobs_research} />}
    </div>
  );
};

export default Dashboard;