import { createSlice, PayloadAction } from '@reduxjs/toolkit';
import { Itinerary } from '../../services/itineraryApi';

interface ItineraryState {
  currentItinerary: Itinerary | null;
  itineraries: Itinerary[];
  loading: boolean;
  error: string | null;
}

const initialState: ItineraryState = {
  currentItinerary: null,
  itineraries: [],
  loading: false,
  error: null,
};

const itinerarySlice = createSlice({
  name: 'itinerary',
  initialState,
  reducers: {
    setCurrentItinerary: (state, action: PayloadAction<Itinerary | null>) => {
      state.currentItinerary = action.payload;
    },
    setItineraries: (state, action: PayloadAction<Itinerary[]>) => {
      state.itineraries = action.payload;
    },
    addItinerary: (state, action: PayloadAction<Itinerary>) => {
      state.itineraries.push(action.payload);
    },
    updateItinerary: (state, action: PayloadAction<Itinerary>) => {
      const index = state.itineraries.findIndex(
        item => item.itinerary_id === action.payload.itinerary_id
      );
      if (index !== -1) {
        state.itineraries[index] = action.payload;
      }
      if (state.currentItinerary?.itinerary_id === action.payload.itinerary_id) {
        state.currentItinerary = action.payload;
      }
    },
    deleteItinerary: (state, action: PayloadAction<string>) => {
      state.itineraries = state.itineraries.filter(
        item => item.itinerary_id !== action.payload
      );
      if (state.currentItinerary?.itinerary_id === action.payload) {
        state.currentItinerary = null;
      }
    },
    setLoading: (state, action: PayloadAction<boolean>) => {
      state.loading = action.payload;
    },
    setError: (state, action: PayloadAction<string | null>) => {
      state.error = action.payload;
    },
  },
});

export const { 
  setCurrentItinerary,
  setItineraries,
  addItinerary,
  updateItinerary,
  deleteItinerary,
  setLoading,
  setError,
} = itinerarySlice.actions;

export default itinerarySlice.reducer;
