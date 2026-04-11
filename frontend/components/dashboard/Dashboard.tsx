import React from 'react';
import { QueryResponse } from '@/lib/types';
import ScheduleCard from '../cards/ScheduleCard';
import DiningCard from '../cards/DiningCard';
import FinanceCard from '../cards/FinanceCard';
import EventsCard from '../cards/EventsCard';
import StudyResourcesCard from '../cards/StudyResourcesCard';
import NavigatorCard from '../cards/NavigatorCard';
import JobsResearchCard from '../cards/JobsResearchCard';
import { motion } from 'framer-motion';

interface DashboardProps {
  data: QueryResponse;
}

const Dashboard: React.FC<DashboardProps> = ({ data }) => {
  const { results } = data;

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {results.schedule && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <ScheduleCard data={results.schedule} />
        </motion.div>
      )}
      {results.dining && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <DiningCard data={results.dining} />
        </motion.div>
      )}
      {results.finance && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <FinanceCard data={results.finance} />
        </motion.div>
      )}
      {results.events && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <EventsCard data={results.events} />
        </motion.div>
      )}
      {results.study_resources && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <StudyResourcesCard data={results.study_resources} />
        </motion.div>
      )}
      {results.navigator && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <NavigatorCard data={results.navigator} />
        </motion.div>
      )}
      {results.jobs_research && (
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
          <JobsResearchCard data={results.jobs_research} />
        </motion.div>
      )}
    </div>
  );
};

export default Dashboard;