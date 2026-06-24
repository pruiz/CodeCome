import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { auditsApi, usersApi, workersApi } from '../services/api';

function ToggleSwitch({ checked, label, description, onChange }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-4 rounded border border-gray-700 bg-gray-700 px-3 py-2 text-left text-sm hover:border-cyan-700"
    >
      <span>
        <span className="block text-gray-100">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-gray-400">{description}</span>}
      </span>
      <span className={`relative h-6 w-11 flex-shrink-0 rounded-full border transition ${checked ? 'border-cyan-500 bg-cyan-500/40' : 'border-gray-600 bg-gray-800'}`}>
        <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${checked ? 'translate-x-5' : 'translate-x-0'}`} />
      </span>
    </button>
  );
}

export default function AuditCreator() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    sourceType: 'local',
    sourceLocation: '',
    codecomeYml: '',
    workerId: '',
    modelId: '',
    questionOwnerUserId: '',
    autoContinue: false,
  });
  const [file, setFile] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [workerModels, setWorkerModels] = useState([]);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    workersApi.list()
      .then((data) => {
        setWorkers(data.workers || []);
        const firstAvailable = (data.workers || []).find((worker) => worker.status !== 'disabled' && worker.status !== 'offline');
        if (firstAvailable) {
          setFormData((current) => ({ ...current, workerId: String(firstAvailable.id) }));
        }
      })
      .catch((error) => console.error('Failed to load workers:', error));
    usersApi.list({ active: true, limit: 500 })
      .then((data) => setUsers(data.users || []))
      .catch((error) => console.error('Failed to load users:', error));
  }, []);

  useEffect(() => {
    if (!formData.workerId) {
      setWorkerModels([]);
      setFormData((current) => ({ ...current, modelId: '' }));
      return;
    }
    workersApi.models(formData.workerId)
      .then((data) => setWorkerModels(data.models || []))
      .catch(() => setWorkerModels([]));
  }, [formData.workerId]);

  const modelSettings = formData.modelId
    ? { __audit_options: { worker_model: formData.modelId } }
    : undefined;
  
  const handleSubmit = async () => {
    setLoading(true);
    try {
      if (formData.sourceType === 'zip' && file) {
        const result = await auditsApi.uploadZip({ ...formData, file, modelSettings });
        navigate(`/audit/${result.id}`);
      } else {
        const result = await auditsApi.create({
          name: formData.name,
          source_type: formData.sourceType,
          source_location: formData.sourceLocation,
          codecome_yml: formData.codecomeYml,
          model_settings: modelSettings,
          worker_id: formData.workerId ? Number(formData.workerId) : undefined,
          question_owner_user_id: formData.questionOwnerUserId ? Number(formData.questionOwnerUserId) : undefined,
          auto_continue: formData.autoContinue,
        });
        navigate(`/audit/${result.id}`);
      }
    } catch (error) {
      alert(`Failed to create audit: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };
  
  return (
    <div className="max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">Create New Audit</h2>
      
      {/* Progress */}
      <div className="flex items-center gap-2 mb-6">
        {[1, 2, 3].map(i => (
          <React.Fragment key={i}>
            <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold ${
              i <= step ? 'bg-blue-600 text-white' : 'bg-gray-600 text-gray-400'
            }`}>
              {i}
            </div>
            {i < 3 && <div className={`flex-1 h-0.5 ${i < step ? 'bg-blue-600' : 'bg-gray-600'}`}></div>}
          </React.Fragment>
        ))}
      </div>
      
      {/* Step 1: Source */}
      {step === 1 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <h3 className="text-lg font-semibold mb-4">Source Code</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-2">Type</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourceType"
                    value="local"
                    checked={formData.sourceType === 'local'}
                    onChange={(e) => setFormData({ ...formData, sourceType: e.target.value })}
                  />
                  <span>Local Directory</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourceType"
                    value="zip"
                    checked={formData.sourceType === 'zip'}
                    onChange={(e) => setFormData({ ...formData, sourceType: e.target.value })}
                  />
                  <span>Upload ZIP</span>
                </label>
                <label className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="sourceType"
                    value="git"
                    checked={formData.sourceType === 'git'}
                    onChange={(e) => setFormData({ ...formData, sourceType: e.target.value })}
                  />
                  <span>Git URL</span>
                </label>
              </div>
            </div>
            
            {formData.sourceType === 'local' && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">Path to source code</label>
                <input
                  type="text"
                  value={formData.sourceLocation}
                  onChange={(e) => setFormData({ ...formData, sourceLocation: e.target.value })}
                  placeholder="/path/to/source/code"
                  className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600"
                />
              </div>
            )}
            
            {formData.sourceType === 'zip' && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">Upload ZIP file</label>
                <input
                  type="file"
                  accept=".zip,.tar.gz,.tgz"
                  onChange={(e) => {
                    setFile(e.target.files[0]);
                    setFormData({ ...formData, sourceLocation: e.target.files[0]?.name || '' });
                  }}
                  className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600"
                />
              </div>
            )}
            
            {formData.sourceType === 'git' && (
              <div>
                <label className="block text-sm font-medium text-gray-400 mb-1">Git repository URL</label>
                <input
                  type="text"
                  value={formData.sourceLocation}
                  onChange={(e) => setFormData({ ...formData, sourceLocation: e.target.value })}
                  placeholder="https://github.com/user/repo"
                  className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600"
                />
              </div>
            )}
          </div>
          
          <div className="flex justify-end mt-6">
            <button
              onClick={() => setStep(2)}
              disabled={!formData.sourceLocation && !file}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-semibold"
            >
              Next
            </button>
          </div>
        </div>
      )}
      
      {/* Step 2: Configuration */}
      {step === 2 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <h3 className="text-lg font-semibold mb-4">Configuration</h3>
          
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Audit Name</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="My Audit"
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600"
              />
            </div>

            <div>
              <label htmlFor="workerModel" className="block text-sm font-medium text-gray-400 mb-1">Worker Model</label>
              <select
                id="workerModel"
                value={formData.modelId}
                onChange={(e) => setFormData({ ...formData, modelId: e.target.value })}
                disabled={!formData.workerId || workerModels.length === 0}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">Use default model</option>
                {workerModels.map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
              </select>
              <p className="text-xs text-gray-500 mt-1">When selected, passed as the default <code>CODECOME_MODEL</code>. Audit-wide and per-phase environment settings can override it.</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-400 mb-1">Worker</label>
              <select
                value={formData.workerId}
                onChange={(e) => setFormData({ ...formData, workerId: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600"
              >
                <option value="">Auto-select available worker</option>
                {workers.map((worker) => (
                  <option key={worker.id} value={worker.id}>
                    {worker.name} ({worker.type}, {worker.status}, {worker.current_jobs}/{worker.max_concurrent_jobs})
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">
                Workers can be local, SSH hosts, Proxmox VMs, or Proxmox LXCs. This build executes local workers first; remote execution is the next adapter.
              </p>
            </div>

            <div>
              <label htmlFor="questionOwner" className="block text-sm font-medium text-gray-400 mb-1">Question Owner</label>
              <select
                id="questionOwner"
                value={formData.questionOwnerUserId}
                onChange={(e) => setFormData({ ...formData, questionOwnerUserId: e.target.value })}
                className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600"
              >
                <option value="">No owner</option>
                {users.map((user) => (
                  <option key={user.id} value={user.id}>{user.display_name} ({user.is_llm_user ? 'AI' : 'Human'})</option>
                ))}
              </select>
              <p className="text-xs text-gray-500 mt-1">Blocking phase questions are assigned to this user. AI users can auto-answer.</p>
            </div>
             
            <ToggleSwitch
              checked={formData.autoContinue}
              label="Auto-continue to next phase"
              description="Automatically queue the next CodeCome command after successful phases unless blocking questions are found."
              onChange={(value) => setFormData({ ...formData, autoContinue: value })}
            />
          </div>
          
          <div className="flex justify-between mt-6">
            <button
              onClick={() => setStep(1)}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-white rounded"
            >
              Back
            </button>
            <button
              onClick={() => setStep(3)}
              disabled={!formData.name}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-semibold"
            >
              Next
            </button>
          </div>
        </div>
      )}
      
      {/* Step 3: Review */}
      {step === 3 && (
        <div className="bg-gray-800 rounded-lg border border-gray-700 p-6">
          <h3 className="text-lg font-semibold mb-4">Review & Create</h3>
          
          <div className="space-y-2 text-sm">
            <p><span className="text-gray-400">Name:</span> {formData.name}</p>
            <p><span className="text-gray-400">Source:</span> {formData.sourceType === 'zip' ? (file?.name || 'ZIP file') : formData.sourceLocation}</p>
            <p><span className="text-gray-400">Worker:</span> {workers.find((worker) => String(worker.id) === formData.workerId)?.name || 'Auto-select'}</p>
            <p><span className="text-gray-400">Model:</span> {formData.modelId || 'Default'}</p>
            <p><span className="text-gray-400">Question Owner:</span> {users.find((user) => String(user.id) === formData.questionOwnerUserId)?.display_name || 'None'}</p>
            <p><span className="text-gray-400">Auto-continue:</span> {formData.autoContinue ? 'Yes' : 'No'}</p>
          </div>
          
          <div className="flex justify-between mt-6">
            <button
              onClick={() => setStep(2)}
              className="px-4 py-2 bg-gray-600 hover:bg-gray-500 text-white rounded"
            >
              Back
            </button>
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded font-semibold"
            >
              {loading ? 'Creating...' : 'Create Audit'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
