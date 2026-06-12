import Home from '../pages/Home';
import RequirementForm from '../pages/RequirementForm';
import ItineraryList from '../pages/ItineraryList';
import ItineraryDetail from '../pages/ItineraryDetail';
import TaskStatus from '../pages/TaskStatus';
import Login from '../pages/Login';
import Profile from '../pages/Profile';
import ForgotPassword from '../pages/ForgotPassword';
export const routes = [
  {
    path: '/',
    element: <Home />,
  },
  {
    path: '/requirement',
    element: <RequirementForm />,
  },
  {
    path: '/itineraries',
    element: <ItineraryList />,
  },
  {
    path: '/itinerary/:id',
    element: <ItineraryDetail />,
  },
  {
    path: '/task/:taskId',
    element: <TaskStatus />,
  },
  {
    path: '/login',
    element: <Login />,
  },
  {
    path: '/forgot-password',
    element: <ForgotPassword />,
  },
  {
    path: '/reset-password',
    element: <ForgotPassword />,
  },
  {
    path: '/profile',
    element: <Profile />,
  },
];

