import { create } from 'zustand';
const labels = ['Fresh Juices and Smoothies', 'Pastries and Warm Desserts', 'Breakfast and Sandwiches', 'VeryLongCourseNameWithoutSpacesForRegressionTesting', 'العصائر الطازجة والمشروبات المخفوقة'];
export const usePOSStore = create((set) => ({
  selectedCategory: '', setSelectedCategory: (selectedCategory: string) => set({selectedCategory}),
  menuItems: labels.flatMap((course, i) => Array.from({length: i === 0 ? 1000 : 4}, (_, n) => ({id:`${i}-${n}`,course}))),
  categories: labels.map(name => ({name,label:name,icon:'food'})),
  orderComment: '', setOrderComment: () => {},
}));
