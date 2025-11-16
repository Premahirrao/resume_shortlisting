import React, { useState } from 'react';
import '@/App.css';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { Upload, FileText, Trophy, Github, Code, Award } from 'lucide-react';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

function App() {
  const [jobDescription, setJobDescription] = useState('');
  const [resumeFiles, setResumeFiles] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [results, setResults] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [currentStep, setCurrentStep] = useState(0);

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    setResumeFiles(files);
    toast.success(`${files.length} file(s) selected`);
  };

  const removeFile = (index) => {
    const newFiles = resumeFiles.filter((_, i) => i !== index);
    setResumeFiles(newFiles);
    toast.success('File removed');
  };

  const toggleExpanded = (id) => {
    setExpanded((s) => ({ ...s, [id]: !s[id] }));
  };

  const downloadResults = () => {
    if (!results) return;
    const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'results.json';
    a.click();
    URL.revokeObjectURL(url);
    toast.success('Results downloaded');
  };

  const handleProcess = async () => {
    if (!jobDescription) {
      toast.error('Please enter job description');
      return;
    }

    if (resumeFiles.length === 0) {
      toast.error('Please upload at least one resume');
      return;
    }

    setProcessing(true);
    setResults(null);

    try {
      setCurrentStep(1); // Step 1: Text Extraction & Translation
      const formData = new FormData();
      formData.append('job_description', jobDescription);
      formData.append('google_credentials', '');  // No longer needed, but kept for API compatibility

      resumeFiles.forEach((file) => {
        formData.append('resume_files', file);
      });

      // Simulate step progression
      setTimeout(() => setCurrentStep(2), 2000); // Step 2: Bi-Encoder
      setTimeout(() => setCurrentStep(3), 4000); // Step 3: Cross-Encoder
      setTimeout(() => setCurrentStep(4), 6000); // Step 4: Social Score

      const response = await axios.post(`${API}/process`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
        timeout: 300000, // 5 minutes
      });

      setCurrentStep(5); // Step 5: Final Results
      setResults(response.data);
      toast.success('Processing completed!');
    } catch (error) {
      console.error('Processing error:', error);
      toast.error(error.response?.data?.detail || 'Processing failed');
      setCurrentStep(0);
    } finally {
      setProcessing(false);
      setTimeout(() => setCurrentStep(0), 1000);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-indigo-50">
      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-bold text-slate-800 mb-3" style={{ fontFamily: 'Space Grotesk, sans-serif' }}>
            AI Resume Shortlisting System
          </h1>
          <p className="text-lg text-slate-600" style={{ fontFamily: 'Inter, sans-serif' }}>
            Handwritten • Multilingual • Context-Aware • Social Score
          </p>
        </div>

        {/* Main Form */}
        <div className="grid grid-cols-1 gap-6 mb-8">
          {/* Job Description */}
          <Card data-testid="job-description-card" className="shadow-md">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="w-5 h-5" />
                Job Description
              </CardTitle>
              <CardDescription>Enter the job description</CardDescription>
            </CardHeader>
            <CardContent>
              <Textarea
                data-testid="job-description-input"
                placeholder="Paste job description here...\n\nExample: Looking for a Senior Software Engineer with 5+ years experience in React, Node.js, and MongoDB..."
                value={jobDescription}
                onChange={(e) => setJobDescription(e.target.value)}
                className="min-h-[200px] font-mono text-sm"
              />
            </CardContent>
          </Card>
        </div>

        {/* Upload Section */}
        <Card data-testid="upload-card" className="shadow-md mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="w-5 h-5" />
              Upload Resumes
            </CardTitle>
            <CardDescription>Upload multiple resume files (PDF, JPG, PNG)</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center hover:border-blue-400 transition-colors">
              <Input
                data-testid="resume-file-input"
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={handleFileChange}
                className="hidden"
                id="resume-upload"
              />
              <label htmlFor="resume-upload" className="cursor-pointer">
                <Upload className="w-12 h-12 mx-auto mb-4 text-slate-400" />
                <p className="text-slate-600 font-medium mb-2">Click to upload resumes</p>
                <p className="text-sm text-slate-500">PDF, JPG, PNG supported</p>
              </label>
              {resumeFiles.length > 0 && (
                <div className="mt-4 text-left">
                  <p className="font-medium text-slate-700 mb-2">{resumeFiles.length} file(s) selected:</p>
                  <ul className="text-sm text-slate-600 space-y-1">
                    {resumeFiles.map((file, idx) => (
                      <li key={idx} className="flex items-center justify-between">
                        <span className="truncate">• {file.name}</span>
                        <button className="text-sm text-red-600 ml-4" onClick={() => removeFile(idx)}>Remove</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Processing Steps */}
        {processing && (
          <Card className="shadow-md mb-8">
            <CardHeader>
              <CardTitle>Processing Steps</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className={`flex items-center gap-3 p-3 rounded ${currentStep >= 1 ? 'bg-green-50 border-l-4 border-green-500' : 'bg-slate-50'}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${currentStep >= 1 ? 'bg-green-500 text-white' : 'bg-slate-300 text-slate-600'}`}>
                    {currentStep > 1 ? '✓' : '1'}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">Text Extraction & Translation</p>
                    <p className="text-sm text-slate-600">Extracting text from resumes and translating to English</p>
                  </div>
                </div>
                <div className={`flex items-center gap-3 p-3 rounded ${currentStep >= 2 ? 'bg-green-50 border-l-4 border-green-500' : 'bg-slate-50'}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${currentStep >= 2 ? 'bg-green-500 text-white' : 'bg-slate-300 text-slate-600'}`}>
                    {currentStep > 2 ? '✓' : '2'}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">Bi-Encoder Initial Ranking</p>
                    <p className="text-sm text-slate-600">Calculating initial semantic similarity scores</p>
                  </div>
                </div>
                <div className={`flex items-center gap-3 p-3 rounded ${currentStep >= 3 ? 'bg-green-50 border-l-4 border-green-500' : 'bg-slate-50'}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${currentStep >= 3 ? 'bg-green-500 text-white' : 'bg-slate-300 text-slate-600'}`}>
                    {currentStep > 3 ? '✓' : '3'}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">Cross-Encoder Refinement</p>
                    <p className="text-sm text-slate-600">Refining scores with deep relevance analysis</p>
                  </div>
                </div>
                <div className={`flex items-center gap-3 p-3 rounded ${currentStep >= 4 ? 'bg-green-50 border-l-4 border-green-500' : 'bg-slate-50'}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${currentStep >= 4 ? 'bg-green-500 text-white' : 'bg-slate-300 text-slate-600'}`}>
                    {currentStep > 4 ? '✓' : '4'}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">Social Score Calculation</p>
                    <p className="text-sm text-slate-600">Fetching GitHub, LeetCode, and CodeChef data</p>
                  </div>
                </div>
                <div className={`flex items-center gap-3 p-3 rounded ${currentStep >= 5 ? 'bg-green-50 border-l-4 border-green-500' : 'bg-slate-50'}`}>
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center ${currentStep >= 5 ? 'bg-green-500 text-white' : 'bg-slate-300 text-slate-600'}`}>
                    {currentStep > 5 ? '✓' : '5'}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">Final Ranking</p>
                    <p className="text-sm text-slate-600">Combining scores and generating final results</p>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Process Button */}
        <div className="text-center mb-8">
          <Button
            data-testid="process-button"
            onClick={handleProcess}
            disabled={processing}
            size="lg"
            className="px-8 py-6 text-lg font-semibold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700"
          >
            {processing ? (
              <>
                <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white mr-2"></div>
                Processing...
              </>
            ) : (
              <>Process & Rank Resumes</>
            )}
          </Button>
        </div>

        {/* Results */}
        {results && (
          <>
            {/* Bi-Encoder Initial Ranking */}
            {results.bi_encoder_ranking && results.bi_encoder_ranking.length > 0 && (
              <Card className="shadow-lg mb-6">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="text-blue-600 font-bold">Step 1:</span>
                    Bi-Encoder Initial Ranking ({results.bi_encoder_ranking.length} candidates)
                  </CardTitle>
                  <CardDescription>
                    Initial semantic similarity scores calculated
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {results.bi_encoder_ranking.map((candidate, index) => (
                      <div key={candidate.resume_id} className="flex items-center justify-between p-3 bg-blue-50 rounded-lg border-l-4 border-blue-500">
                        <div className="flex items-center gap-3">
                          <span className="bg-blue-600 text-white rounded-full w-8 h-8 flex items-center justify-center text-sm font-bold">
                            {index + 1}
                          </span>
                          <div>
                            <p className="font-medium">{candidate.filename}</p>
                            <p className="text-sm text-slate-600">
                              {candidate.translated && <span className="text-blue-600">Translated from {candidate.language}</span>}
                            </p>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-2xl font-bold text-blue-600">{candidate.bi_encoder_score.toFixed(1)}%</p>
                          <p className="text-xs text-slate-500">Bi-Encoder Score</p>
                        </div>
                        {index < Math.min(20, results.bi_encoder_ranking.length) && (
                          <span className="text-green-600 font-semibold ml-2">→ Selected for Cross-Encoder</span>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Cross-Encoder Refined Ranking */}
            {results.cross_encoder_ranking && results.cross_encoder_ranking.length > 0 && (
              <Card className="shadow-lg mb-6">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <span className="text-purple-600 font-bold">Step 2:</span>
                    Cross-Encoder Refined Ranking ({results.cross_encoder_ranking.length} candidates)
                  </CardTitle>
                  <CardDescription>
                    Deep relevance analysis applied to top candidates
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {results.cross_encoder_ranking.map((candidate, index) => (
                      <div key={candidate.resume_id} className="flex items-center justify-between p-3 bg-purple-50 rounded-lg border-l-4 border-purple-500">
                        <div className="flex items-center gap-3">
                          <span className="bg-purple-600 text-white rounded-full w-8 h-8 flex items-center justify-center text-sm font-bold">
                            {index + 1}
                          </span>
                          <div>
                            <p className="font-medium">{candidate.filename}</p>
                            <div className="flex gap-4 text-sm text-slate-600 mt-1">
                              <span>Bi-Encoder: <strong>{candidate.bi_encoder_score.toFixed(1)}%</strong></span>
                              <span>Cross-Encoder: <strong className="text-purple-600">{((candidate.cross_encoder_score % 100).toFixed(1))
                              }%</strong></span>
                            </div>
                          </div>
                        </div>
                        <div className="text-right">
                          <p className="text-2xl font-bold text-purple-600">{((candidate.cross_encoder_score % 100).toFixed(1))
                          }%</p>
                          <p className="text-xs text-slate-500">Refined Score</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Final Results */}
            <Card data-testid="results-card" className="shadow-lg">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Trophy className="w-6 h-6 text-yellow-500" />
                  <span className="text-green-600 font-bold">Final Step:</span>
                  Top 10 Shortlisted Candidates (Cross-Encoder + Social Score)
                </CardTitle>
                <CardDescription>
                  Total processed: {results.total_processed} | Ranked by combined score (70% contextual + 30% social)
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="flex justify-end mb-4">
                  <Button onClick={downloadResults} className="mr-2">Download JSON</Button>
                </div>
                <div className="space-y-4">
                  {results.top_candidates.map((candidate, index) => (
                    <Card key={candidate.resume_id} data-testid={`candidate-${index}`} className="border-l-4 border-l-blue-500">
                      <CardHeader>
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <CardTitle className="text-lg flex items-center gap-2">
                              <span className={`${index === 0 ? 'bg-yellow-500' : 'bg-blue-600'} text-white rounded-full w-10 h-10 flex items-center justify-center text-lg font-bold`}>
                                {index + 1}
                              </span>
                              {candidate.filename}
                            </CardTitle>
                            <div className="mt-2 flex items-center gap-2 flex-wrap">
                              {candidate.language && (
                                <>
                                  <span className="text-xs px-2 py-1 bg-blue-100 text-blue-700 rounded">Language: {candidate.language.toUpperCase()}</span>
                                  {candidate.translated && (
                                    <span className="text-xs px-2 py-1 bg-green-100 text-green-700 rounded">Translated</span>
                                  )}
                                </>
                              )}
                              <CardDescription className="mt-0">
                                Final Score: <span className="font-bold text-purple-600 text-lg">{candidate.combined_score.toFixed(1) % 100}</span>
                              </CardDescription>
                            </div>
                          </div>
                          <div className="ml-4">
                            <button className="text-sm text-slate-600 underline" onClick={() => toggleExpanded(candidate.resume_id)}>{expanded[candidate.resume_id] ? 'Hide' : 'View'}</button>
                          </div>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {expanded[candidate.resume_id] && (
                          <div className="mb-4">
                            <pre className="p-3 bg-white text-sm rounded border">{candidate.resume_text}</pre>
                          </div>
                        )}
                        {/* Score Breakdown */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
                          <div>
                            <Label className="text-xs text-slate-500">Bi-Encoder (Initial)</Label>
                            <Progress value={candidate.bi_encoder_score} className="h-3 mt-1 bg-blue-200" />
                            <p className="text-sm font-medium mt-1 text-blue-600">{candidate.bi_encoder_score.toFixed(1)}%</p>
                          </div>
                          <div>
                            <Label className="text-xs text-slate-500">Cross-Encoder (Refined)</Label>
                            <Progress value={candidate.cross_encoder_score} className="h-3 mt-1 bg-purple-200" />
                            <p className="text-sm font-medium mt-1 text-purple-600">{((candidate.cross_encoder_score % 100).toFixed(1))
}%</p>
                          </div>
                          <div>
                            <Label className="text-xs text-slate-500">Social Score</Label>
                            <Progress value={candidate.social_score} className="h-3 mt-1 bg-orange-200" />
                            <p className="text-sm font-medium mt-1 text-orange-600">{candidate.social_score.toFixed(1)}%</p>
                          </div>
                        </div>

                        {/* Social Stats */}
                        {(candidate.github_data || candidate.leetcode_data || candidate.codechef_data) && (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mt-4 pt-4 border-t">
                            {candidate.github_data && (
                              <div className="flex items-center gap-2 text-sm">
                                <Github className="w-4 h-4 text-slate-600" />
                                <span className="text-slate-600">
                                  {candidate.github_data.public_repos} repos, {candidate.github_data.followers} followers
                                </span>
                              </div>
                            )}
                            {candidate.leetcode_data && (
                              <div className="flex items-center gap-2 text-sm">
                                <Code className="w-4 h-4 text-slate-600" />
                                <span className="text-slate-600">
                                  {candidate.leetcode_data.total_solved} LeetCode problems
                                </span>
                              </div>
                            )}
                            {candidate.codechef_data && (
                              <div className="flex items-center gap-2 text-sm">
                                <Award className="w-4 h-4 text-slate-600" />
                                <span className="text-slate-600">
                                  {candidate.codechef_data.problems_solved} CodeChef problems
                                </span>
                              </div>
                            )}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </CardContent>
            </Card>
          </>
        )}
      </div>
    </div>
  );
}

export default App;
