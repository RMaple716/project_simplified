import { configureStore } from '@reduxjs/toolkit';
import requirementReducer from './slices/requirementSlice';
import itineraryReducer from './slices/itinerarySlice';
import uiReducer from './slices/uiSlice';
import authReducer from './slices/authSlice';

const store = configureStore({
  reducer: {
    requirement: requirementReducer,
    itinerary: itineraryReducer,
    ui: uiReducer,
    auth: authReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

export default store;
