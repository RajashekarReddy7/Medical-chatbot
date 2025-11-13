import React from "react";
import { motion } from "framer-motion";

const Dashboard = () => {
  return (
    <div>
      <h2 className="text-3xl font-semibold mb-4">Welcome to Doctor Triage AI</h2>
      <p className="text-gray-600 dark:text-gray-300 mb-6">
        Analyze symptoms, generate follow-ups, and predict possible conditions.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <motion.div whileHover={{ scale: 1.03 }} className="p-6 bg-white dark:bg-gray-800 shadow-md rounded-2xl">
          <h3 className="text-lg font-semibold mb-2">Total Patients</h3>
          <p className="text-3xl font-bold text-blue-600">234</p>
        </motion.div>

        <motion.div whileHover={{ scale: 1.03 }} className="p-6 bg-white dark:bg-gray-800 shadow-md rounded-2xl">
          <h3 className="text-lg font-semibold mb-2">Ongoing Consultations</h3>
          <p className="text-3xl font-bold text-green-500">12</p>
        </motion.div>

        <motion.div whileHover={{ scale: 1.03 }} className="p-6 bg-white dark:bg-gray-800 shadow-md rounded-2xl">
          <h3 className="text-lg font-semibold mb-2">Model Accuracy</h3>
          <p className="text-3xl font-bold text-yellow-500">94%</p>
        </motion.div>
      </div>
    </div>
  );
};

export default Dashboard;
