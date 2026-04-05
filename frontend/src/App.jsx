import React, { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'

function App() {
  const [searchQuery, setSearchQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [folderPath, setFolderPath] = useState('')
  const [processStatus, setProcessStatus] = useState(null)
  const [progressData, setProgressData] = useState(null)
  const [hoveredVideo, setHoveredVideo] = useState(null)
  const [selectedImage, setSelectedImage] = useState(null)
  const videoRefs = useRef({})
  const progressInterval = useRef(null)

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape' && selectedImage) {
      setSelectedImage(null)
    }
  }, [selectedImage])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  useEffect(() => {
    if (processing) {
      progressInterval.current = setInterval(async () => {
        try {
          const resp = await axios.get(`${API_BASE}/process/status`)
          setProgressData(resp.data)
        } catch (e) {
          console.error('获取进度失败', e)
        }
      }, 500)
    } else {
      if (progressInterval.current) {
        clearInterval(progressInterval.current)
        progressInterval.current = null
      }
      if (!loading) {
        setProgressData(null)
      }
    }
    return () => {
      if (progressInterval.current) {
        clearInterval(progressInterval.current)
      }
    }
  }, [processing, loading])

  const handleSearch = async (e) => {
    if (e) e.preventDefault()
    if (!searchQuery.trim()) return

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/search/`, {
        query: searchQuery,
        top_k: 20
      })
      console.log('搜索结果:', response.data)
      setResults(response.data.results || [])
    } catch (error) {
      console.error('搜索错误:', error)
      setResults([])
    } finally {
      setLoading(false)
    }
  }

  const handleProcess = async () => {
    if (!folderPath.trim()) return

    setProcessing(true)
    setProcessStatus(null)
    setProgressData({
      is_processing: true,
      current_video: '',
      current_video_index: 0,
      total_videos: 0,
      current_frame_index: 0,
      processed_frames: 0,
      status: 'starting'
    })

    try {
      const response = await axios.post(`${API_BASE}/process/`, {
        folder_path: folderPath
      })
      setProcessStatus({
        status: 'success',
        message: response.data.message
      })
    } catch (error) {
      console.error('处理错误:', error)
      setProcessStatus({
        status: 'error',
        message: error.response?.data?.detail || '处理失败'
      })
    } finally {
      setProcessing(false)
    }
  }

  const handleMouseEnter = (result) => {
    setHoveredVideo(result.video_path)
  }

  const handleMouseLeave = () => {
    setHoveredVideo(null)
  }

  const formatTimestamp = (seconds) => {
    if (seconds === undefined || seconds === null) return '--:--'
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const formatTimeRange = (start, end) => {
    return `${formatTimestamp(start)} - ${formatTimestamp(end)}`
  }

  const getScorePercentage = (score) => {
    if (score === undefined || score === null) return '0.0'
    const percentage = Math.max(0, Math.min(100, score))
    return percentage.toFixed(1)
  }

  const handleBrowse = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectFolder()
      if (path) setFolderPath(path)
    } else {
      const input = document.createElement('input')
      input.type = 'file'
      input.webkitdirectory = true
      input.onchange = (e) => {
        const files = e.target.files
        if (files.length > 0) {
          const path = files[0].webkitRelativePath.split('/')[0]
          setFolderPath(path)
        }
      }
      input.click()
    }
  }

  const handleShowInFolder = (videoPath) => {
    if (window.electronAPI) {
      window.electronAPI.showItemInFolder(videoPath)
    } else {
      alert('仅支持 Electron 环境')
    }
  }

  const getFrameUrl = (framePath) => {
    if (!framePath) return ''
    const filename = framePath.split(/[\\/]/).pop()
    return `${API_BASE}/frames/${filename}`
  }

  const getProgressPercent = () => {
    if (!progressData || progressData.total_videos === 0) return 0
    return Math.round((progressData.current_video_index / progressData.total_videos) * 100)
  }

  const formatDate = (dateStr) => {
    if (!dateStr) return ''
    const date = new Date(dateStr)
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  }

  return (
    <div className="app-container">
      {selectedImage && (
        <div
          className="modal-overlay"
          onClick={() => setSelectedImage(null)}
        >
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setSelectedImage(null)}
              className="modal-close"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            <img
              src={selectedImage.url}
              alt={selectedImage.description}
              className="modal-image"
            />
            <div className="modal-info">
              <p className="modal-description">{selectedImage.description}</p>
              <div className="modal-meta">
                <span className="modal-video">{selectedImage.video}</span>
                <span className="modal-time">{formatTimeRange(selectedImage.start_time, selectedImage.end_time)}</span>
              </div>
            </div>
          </div>
        </div>
      )}

      {processing && (
        <div className="processing-overlay">
          <div className="processing-content">
            <div className="processing-icon">
              <svg className="w-16 h-16 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
            <h2 className="processing-title">AI 正在逐帧解析</h2>
            <p className="processing-subtitle">请稍候，画面即将呈现...</p>
            {progressData && (
              <div className="processing-progress">
                <div className="progress-bar">
                  <div className="progress-fill" style={{ width: `${getProgressPercent()}%` }} />
                </div>
                <div className="progress-info">
                  <span className="progress-file">{progressData.current_video || '初始化中...'}</span>
                  <span className="progress-percent">{getProgressPercent()}%</span>
                </div>
                {progressData.total_videos > 0 && (
                  <span className="progress-detail">
                    视频 {progressData.current_video_index} / {progressData.total_videos}
                    {progressData.processed_frames > 0 && ` · 已处理 ${progressData.processed_frames} 帧`}
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="logo">
            <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <span className="logo-text">VideoRAG</span>
          </div>
        </div>

        <div className="sidebar-section">
          <h3 className="sidebar-label">视频文件夹</h3>
          <div className="folder-input">
            <input
              type="text"
              value={folderPath}
              onChange={(e) => setFolderPath(e.target.value)}
              placeholder="选择视频目录..."
              className="folder-path"
            />
            <button onClick={handleBrowse} className="browse-btn">
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
              </svg>
            </button>
          </div>
          <button
            onClick={handleProcess}
            disabled={processing || !folderPath.trim()}
            className="process-btn"
          >
            {processing ? (
              <>
                <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                处理中...
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                处理视频
              </>
            )}
          </button>
        </div>

        <div className="sidebar-section">
          <h3 className="sidebar-label">快捷搜索</h3>
          <div className="quick-tags">
            {['日落', '室内', '人物', '户外', '夜景'].map((tag) => (
              <button
                key={tag}
                onClick={() => setSearchQuery(tag)}
                className="quick-tag"
              >
                {tag}
              </button>
            ))}
          </div>
        </div>

        <div className="sidebar-footer">
          <p className="footer-text">VideoRAG v1.0</p>
          <p className="footer-text">Ollama + ChromaDB</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="main-header">
          <div className="search-container">
            <form onSubmit={handleSearch} className="search-form">
              <svg className="search-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="输入语义描述，搜索相关镜头... (例如: 阳光下弹吉他的老人)"
                className="search-input"
              />
              <button
                type="submit"
                disabled={loading}
                className="search-btn"
              >
                {loading ? (
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  '搜索'
                )}
              </button>
            </form>
          </div>
        </header>

        <div className="content-area">
          {loading ? (
            <div className="loading-container">
              <div className="loading-spinner">
                <svg className="w-12 h-12 animate-spin" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="2" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
              </div>
              <p className="loading-text">正在检索...</p>
            </div>
          ) : results.length > 0 ? (
            <>
              <div className="results-header">
                <span className="results-count">
                  找到 <strong>{results.length}</strong> 个相关镜头
                </span>
              </div>
              <div className="results-grid">
                {results.map((result, index) => (
                  <div
                    key={`${result.video_path}-${result.timestamp}-${index}`}
                    className="result-card"
                    onMouseEnter={() => handleMouseEnter(result)}
                    onMouseLeave={handleMouseLeave}
                  >
                    <div className="card-thumbnail">
                      {hoveredVideo === result.video_path ? (
                        <video
                          ref={(el) => (videoRefs.current[result.video_path] = el)}
                          src={`file://${result.video_path}#t=${result.start_time || 0}`}
                          muted
                          loop
                          playsInline
                          className="card-video"
                          onMouseEnter={(e) => {
                            e.target.play().catch(() => {})
                          }}
                          onMouseLeave={(e) => {
                            e.target.pause()
                            e.target.currentTime = 0
                          }}
                        />
                      ) : (
                        <img
                          src={getFrameUrl(result.frame_path)}
                          alt={result.description}
                          className="card-image"
                          onClick={() => setSelectedImage({
                            url: getFrameUrl(result.frame_path),
                            description: result.description,
                            video: (result.video_path || '').split(/[\\/]/).pop(),
                            start_time: result.start_time,
                            end_time: result.end_time
                          })}
                          onError={(e) => {
                            e.target.src = `file://${result.frame_path}`
                          }}
                        />
                      )}
                      <div className="card-overlay">
                        <button
                          className="folder-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            handleShowInFolder(result.video_path)
                          }}
                          title="在文件夹中显示"
                        >
                          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                          </svg>
                        </button>
                      </div>
                      <div className="match-badge">
                        {getScorePercentage(result.score)}% 匹配
                        <span style={{opacity:0.5, fontSize:'10px', marginLeft:'4px'}}>({result.score})</span>
                      </div>
                    </div>
                    <div className="card-info">
                      <div className="card-header">
                        <span className="card-time">
                          {result.start_time !== undefined ? formatTimeRange(result.start_time, result.end_time) : formatTimestamp(result.timestamp)}
                        </span>
                      </div>
                      <p className="card-description">{result.description}</p>
                      <div className="card-footer">
                        <span className="card-filename">
                          {(result.video_path || '').split(/[\\/]/).pop()}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <div className="empty-icon">
                <svg className="w-24 h-24" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
                </svg>
              </div>
              <h3 className="empty-title">未找到相关镜头</h3>
              <p className="empty-description">
                请先处理视频文件夹，然后输入语义描述进行搜索<br/>
                例如："户外日落"、"会议室内"、"弹吉他的人"
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}

export default App
