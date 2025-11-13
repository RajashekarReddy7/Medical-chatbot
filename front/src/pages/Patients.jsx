import React, { useEffect, useState } from "react";
import axios from "axios";

const Patients = () => {
  const [patients, setPatients] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await axios.get("http://127.0.0.1:8000/api/patients");
        setPatients(res.data || []);
      } catch (err) {
        console.error("Error fetching patients:", err);
      }
    };
    fetchData();
  }, []);

  return (
    <div>
      <h2 className="text-2xl font-semibold mb-4">Patient Consultations</h2>
      <div className="overflow-x-auto">
        <table className="min-w-full border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
          <thead className="bg-blue-600 text-white">
            <tr>
              <th className="py-2 px-3 text-left">Email</th>
              <th className="py-2 px-3 text-left">Triage Level</th>
              <th className="py-2 px-3 text-left">Summary</th>
              <th className="py-2 px-3 text-left">Date</th>
            </tr>
          </thead>
          <tbody className="bg-white dark:bg-gray-800">
            {patients.length === 0 ? (
              <tr>
                <td colSpan="4" className="text-center py-4 text-gray-500">
                  No consultations yet.
                </td>
              </tr>
            ) : (
              patients.map((p, idx) => (
                <tr
                  key={idx}
                  className="border-t border-gray-200 dark:border-gray-700"
                >
                  <td className="py-2 px-3">{p.email}</td>
                  <td className="py-2 px-3 text-blue-600 font-semibold">
                    {p.triage?.level || "-"}
                  </td>
                  <td className="py-2 px-3">
                    {p.summary_file ? (
                      <a
                        href={`http://127.0.0.1:8000/get_summary/${p.summary_file}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-500 hover:underline"
                      >
                        View Summary
                      </a>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="py-2 px-3">
                    {new Date(p.created_at).toLocaleString()}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default Patients;
