import { Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import BreakpointGate from './components/BreakpointGate';
import Dashboard from './pages/Dashboard';
import Resumes from './pages/Resumes';
import ProfileEdit from './pages/ProfileEdit';
import Board from './pages/Board';
import JobDetail from './pages/JobDetail';
import JobNew from './pages/JobNew';
import ConfirmationPage from './pages/ConfirmationPage';
import PendingEvents from './pages/PendingEvents';
import Schedule from './pages/Schedule';
import Stats from './pages/Stats';
import Settings from './pages/Settings';

export default function App() {
  return (
    <BreakpointGate>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="resumes" element={<Resumes />} />
          <Route path="profile" element={<ProfileEdit />} />
          <Route path="board" element={<Board />} />
          <Route path="jobs/new" element={<JobNew />} />
          <Route path="jobs/:id" element={<JobDetail />} />
          <Route path="confirmations/:id" element={<ConfirmationPage />} />
          <Route path="events" element={<PendingEvents />} />
          <Route path="schedule" element={<Schedule />} />
          <Route path="stats" element={<Stats />} />
          <Route path="settings" element={<Settings />} />
        </Route>
      </Routes>
    </BreakpointGate>
  );
}
