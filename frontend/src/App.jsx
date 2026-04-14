import React, { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'

const API_BASE = 'http://localhost:8000'
const WS_URL = 'ws://localhost:8000/ws/progress'

function App() {
  const [searchQuery, setSearchQuery] = useState('')
  const [results, setResults] = useState([])
  const [loading, setLoading] = useState(false)
  const [processing, setProcessing] = useState(false)
  const [folderPath, setFolderPath] = useState('')
  const [processStatus, setProcessStatus] = useState(null)
  const [progressData, setProgressData] = useState(null)
  const [selectedImage, setSelectedImage] = useState(null)
  const [failedImages, setFailedImages] = useState({})
  const [hoveredVideo, setHoveredVideo] = useState(null)
  const [selectedResults, setSelectedResults] = useState(new Set())
  const [viewMode, setViewMode] = useState('search')
  const [videoList, setVideoList] = useState([])
  const [filterOptions, setFilterOptions] = useState(null)
  const [activeFilters, setActiveFilters] = useState({
    minScore: 0,
    shotSize: '',
    cameraMovement: '',
    lighting: ''
  })
  const [stats, setStats] = useState({ total_videos: 0, total_frames: 0 })
  const videoRefs = useRef({})
  const progressInterval = useRef(null)
  const playerRef = useRef(null)

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

  // WebSocket实时进度连接
  useEffect(() => {
    let ws = null
    let wsConnected = false

    const connectWs = () => {
      try {
        ws = new WebSocket(WS_URL)

        ws.onopen = () => {
          console.log('[WS] 已连接')
          wsConnected = true
        }

        ws.onmessage = (event) => {
          try {
            const msg = JSON.parse(event.data)
            if (msg.type === 'progress' && msg.data) {
              const data = msg.data
              setProgressData(prev => ({
                ...prev,
                current_video: data.current_video || prev?.current_video,
                current_video_index: data.current_video_index || prev?.current_video_index,
                total_videos: data.total_videos || prev?.total_videos,
                status: data.status || 'processing',
                message: data.message || data.current_video,
                processed_videos: data.processed_videos ?? prev?.processed_videos,
                processed_frames: data.processed_frames ?? prev?.processed_frames,
                total_frames: data.total_frames ?? prev?.total_frames
              }))
              if (data.status === 'completed') {
                setProcessing(false)
              }
            }
          } catch (e) {
            console.error('[WS] 解析消息失败', e)
          }
        }

        ws.onerror = (e) => {
          console.error('[WS] 连接错误', e)
        }

        ws.onclose = () => {
          console.log('[WS] 已断开')
          wsConnected = false
          // 自动重连
          if (processing && !wsConnected) {
            setTimeout(connectWs, 2000)
          }
        }
      } catch (e) {
        console.error('[WS] 创建连接失败', e)
      }
    }

    if (processing) {
      connectWs()
    }

    return () => {
      if (ws) {
        ws.close()
      }
    }
  }, [processing])

  useEffect(() => {
    loadVideoList()
    loadFilterOptions()
    loadStats()
  }, [])

  const loadVideoList = async () => {
    try {
      const resp = await axios.get(`${API_BASE}/process/videos`)
      if (resp.data.videos) {
        setVideoList(resp.data.videos)
      }
    } catch (e) {
      console.error('获取视频列表失败', e)
    }
  }

  const loadFilterOptions = async () => {
    try {
      const resp = await axios.get(`${API_BASE}/search/filters/options`)
      setFilterOptions(resp.data)
    } catch (e) {
      console.error('获取筛选选项失败', e)
    }
  }

  const loadStats = async () => {
    try {
      const resp = await axios.get(`${API_BASE}/search/stats`)
      setStats(resp.data)
    } catch (e) {
      console.error('获取统计信息失败', e)
    }
  }

  const handleSearch = async (e) => {
    if (e) e.preventDefault()
    if (!searchQuery.trim()) return

    setLoading(true)
    setViewMode('search')
    try {
      const response = await axios.post(`${API_BASE}/search/`, {
        query: searchQuery,
        top_k: 50,
        filters: activeFilters.minScore > 0 ? {
          min_score: activeFilters.minScore,
          shot_size: activeFilters.shotSize || undefined,
          camera_movement: activeFilters.cameraMovement || undefined,
          lighting: activeFilters.lighting || undefined
        } : null
      })
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
      loadVideoList()
      loadStats()
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

  const handleWatchFolder = async () => {
    if (!folderPath.trim()) return
    try {
      await axios.post(`${API_BASE}/process/watch`, {
        folder_path: folderPath
      })
      alert('已开始监视文件夹，新视频将自动处理')
    } catch (error) {
      console.error('启动监视失败:', error)
    }
  }

  const handleStopWatch = async () => {
    try {
      await axios.post(`${API_BASE}/process/watch/stop`)
      alert('已停止文件夹监视')
    } catch (error) {
      console.error('停止监视失败:', error)
    }
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
    if (score === undefined || score === null) return '--'
    const s = parseFloat(score)
    if (isNaN(s)) return '--'
    return Math.max(0, Math.min(100, s)).toFixed(1)
  }

  const handleBrowse = async () => {
    if (window.electronAPI) {
      const path = await window.electronAPI.selectFolder()
      if (path) setFolderPath(path)
    }
  }

  const handleShowInFolder = (videoPath) => {
    if (window.electronAPI) {
      window.electronAPI.showItemInFolder(videoPath)
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

  const toggleResultSelection = (resultId) => {
    const newSelected = new Set(selectedResults)
    if (newSelected.has(resultId)) {
      newSelected.delete(resultId)
    } else {
      newSelected.add(resultId)
    }
    setSelectedResults(newSelected)
  }

  const selectAllResults = () => {
    if (selectedResults.size === results.length) {
      setSelectedResults(new Set())
    } else {
      setSelectedResults(new Set(results.map((r, i) => `${r.video_path}-${r.timestamp}-${i}`)))
    }
  }

  const copySelectedToClipboard = () => {
    const selectedItems = results.filter((r, i) =>
      selectedResults.has(`${r.video_path}-${r.timestamp}-${i}`)
    )
    const text = selectedItems.map(r =>
      `[${formatTimeRange(r.start_time, r.end_time)}] ${r.video_path}`
    ).join('\n')
    navigator.clipboard.writeText(text)
    alert(`已复制 ${selectedItems.length} 条记录到剪贴板`)
  }

  const exportSelectedPaths = () => {
    const selectedItems = results.filter((r, i) =>
      selectedResults.has(`${r.video_path}-${r.timestamp}-${i}`)
    )
    const text = selectedItems.map(r => r.video_path).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'video_paths.txt'
    a.click()
    URL.revokeObjectURL(url)
  }

  const playVideoPreview = (result) => {
    setSelectedImage({
      url: `file://${result.video_path}`,
      description: result.description,
      video: result.video_path,
      start_time: result.start_time,
      end_time: result.end_time,
      isVideo: true,
      frameUrl: getFrameUrl(result.frame_path)
    })
  }

  return (
    <div className="app-container">
      {selectedImage && (
        <div className="modal-overlay" onClick={() => setSelectedImage(null)}>
          <div className="modal-content video-modal" onClick={(e) => e.stopPropagation()}>
            <button className="modal-close" onClick={() => setSelectedImage(null)}>
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
            {selectedImage.isVideo ? (
              <>
                <video
                  ref={playerRef}
                  src={selectedImage.url}
                  className="preview-video"
                  controls
                  autoPlay
                  onLoadedMetadata={(e) => {
                    if (selectedImage.start_time) {
                      e.target.currentTime = selectedImage.start_time
                    }
                  }}
                />
                <div className="preview-info">
                  <img
                    src={selectedImage.frameUrl}
                    alt={selectedImage.description}
                    className="preview-thumbnail"
                  />
                  <div className="preview-meta">
                    <p className="preview-description">{selectedImage.description}</p>
                    <div className="preview-tags">
                      <span className="preview-video-name">
                        {selectedImage.video.split(/[\\/]/).pop()}
                      </span>
                      <span className="preview-time">
                        {formatTimeRange(selectedImage.start_time, selectedImage.end_time)}
                      </span>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <>
                <img src={selectedImage.url} alt={selectedImage.description} className="modal-image" />
                <div className="modal-info">
                  <p className="modal-description">{selectedImage.description}</p>
                  <div className="modal-meta">
                    <span className="modal-video">{selectedImage.video}</span>
                    <span className="modal-time">{formatTimeRange(selectedImage.start_time, selectedImage.end_time)}</span>
                  </div>
                </div>
              </>
            )}
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

        <div className="sidebar-tabs">
          <button
            className={`sidebar-tab ${viewMode === 'search' ? 'active' : ''}`}
            onClick={() => setViewMode('search')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            搜索
          </button>
          <button
            className={`sidebar-tab ${viewMode === 'media' ? 'active' : ''}`}
            onClick={() => setViewMode('media')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            媒体池
          </button>
          <button
            className={`sidebar-tab ${viewMode === 'filters' ? 'active' : ''}`}
            onClick={() => setViewMode('filters')}
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
            筛选
          </button>
        </div>

        {viewMode === 'search' && (
          <>
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
              <button onClick={handleProcess} disabled={processing || !folderPath.trim()} className="process-btn">
                {processing ? '处理中...' : '处理视频'}
              </button>
              <div className="watch-buttons">
                <button onClick={handleWatchFolder} className="watch-btn">监视文件夹</button>
                <button onClick={handleStopWatch} className="watch-btn stop">停止监视</button>
              </div>
            </div>

            <div className="sidebar-section">
              <h3 className="sidebar-label">快捷搜索</h3>
              <div className="quick-tags">
                {['日落', '室内', '人物', '户外', '夜景', '运动'].map((tag) => (
                  <button key={tag} onClick={() => setSearchQuery(tag)} className="quick-tag">
                    {tag}
                  </button>
                ))}
              </div>
            </div>
          </>
        )}

        {viewMode === 'media' && (
          <div className="sidebar-section media-pool">
            <h3 className="sidebar-label">已处理视频 ({videoList.length})</h3>
            <div className="media-list">
              {videoList.map((video, idx) => (
                <div key={idx} className="media-item">
                  <div className="media-info">
                    <span className="media-name">{video.video_path.split(/[\\/]/).pop()}</span>
                    <span className="media-meta">{video.frame_count} 帧</span>
                  </div>
                </div>
              ))}
              {videoList.length === 0 && (
                <p className="empty-text">暂无已处理视频</p>
              )}
            </div>
          </div>
        )}

        {viewMode === 'filters' && (
          <div className="sidebar-section filter-panel">
            <h3 className="sidebar-label">筛选条件</h3>

            <div className="filter-group">
              <label>最低匹配度</label>
              <div className="filter-slider">
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={activeFilters.minScore}
                  onChange={(e) => setActiveFilters({...activeFilters, minScore: parseInt(e.target.value)})}
                />
                <span>{activeFilters.minScore}%</span>
              </div>
            </div>

            {filterOptions && (
              <>
                <div className="filter-group">
                  <label>景别</label>
                  <select
                    value={activeFilters.shotSize}
                    onChange={(e) => setActiveFilters({...activeFilters, shotSize: e.target.value})}
                  >
                    <option value="">全部</option>
                    {filterOptions.shot_sizes?.map(s => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <label>运镜</label>
                  <select
                    value={activeFilters.cameraMovement}
                    onChange={(e) => setActiveFilters({...activeFilters, cameraMovement: e.target.value})}
                  >
                    <option value="">全部</option>
                    {filterOptions.camera_movements?.map(c => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                </div>

                <div className="filter-group">
                  <label>光影</label>
                  <select
                    value={activeFilters.lighting}
                    onChange={(e) => setActiveFilters({...activeFilters, lighting: e.target.value})}
                  >
                    <option value="">全部</option>
                    {filterOptions.lightings?.map(l => (
                      <option key={l} value={l}>{l}</option>
                    ))}
                  </select>
                </div>
              </>
            )}

            <button onClick={handleSearch} className="apply-filter-btn">应用筛选</button>
          </div>
        )}

        <div className="sidebar-stats">
          <div className="stat-item">
            <span className="stat-value">{stats.total_videos}</span>
            <span className="stat-label">视频</span>
          </div>
          <div className="stat-item">
            <span className="stat-value">{stats.total_frames}</span>
            <span className="stat-label">帧</span>
          </div>
        </div>

        <div className="sidebar-footer">
          <p className="footer-text">VideoRAG V2.0</p>
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
                placeholder="输入语义描述，搜索相关镜头..."
                className="search-input"
              />
              <button type="submit" disabled={loading} className="search-btn">
                {loading ? '搜索中...' : '搜索'}
              </button>
            </form>
          </div>
        </header>

        {results.length > 0 && (
          <div className="batch-toolbar">
            <span className="batch-info">已选择 {selectedResults.size} / {results.length}</span>
            <button onClick={selectAllResults} className="batch-btn">
              {selectedResults.size === results.length ? '取消全选' : '全选'}
            </button>
            <button onClick={copySelectedToClipboard} className="batch-btn" disabled={selectedResults.size === 0}>
              复制到剪贴板
            </button>
            <button onClick={exportSelectedPaths} className="batch-btn" disabled={selectedResults.size === 0}>
              导出素材路径
            </button>
          </div>
        )}

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
                {results.map((result, index) => {
                  const resultId = `${result.video_path}-${result.timestamp}-${index}`
                  const isSelected = selectedResults.has(resultId)
                  return (
                    <div
                      key={resultId}
                      className={`result-card ${isSelected ? 'selected' : ''}`}
                      onMouseEnter={() => setHoveredVideo(result.video_path)}
                      onMouseLeave={() => setHoveredVideo(null)}
                    >
                      <div className="card-checkbox">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleResultSelection(resultId)}
                        />
                      </div>
                      <div className="card-thumbnail">
                        {hoveredVideo === result.video_path ? (
                          <video
                            ref={(el) => (videoRefs.current[result.video_path] = el)}
                            src={`file://${result.video_path}#t=${result.start_time || 0}`}
                            muted
                            loop
                            playsInline
                            className="card-video"
                            onMouseEnter={(e) => e.target.play().catch(() => {})}
                            onMouseLeave={(e) => { e.target.pause(); e.target.currentTime = 0 }}
                          />
                        ) : failedImages[result.frame_path] ? (
                          <div className="card-placeholder">
                            <svg className="w-12 h-12 text-gray-600 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                            </svg>
                            <span className="text-xs text-gray-500">预览图生成中</span>
                          </div>
                        ) : (
                          <img
                            src={getFrameUrl(result.frame_path)}
                            alt={result.description}
                            className="card-image"
                            onClick={() => playVideoPreview(result)}
                            onError={() => setFailedImages(prev => ({ ...prev, [result.frame_path]: true }))}
                          />
                        )}
                        <div className="card-overlay">
                          <button
                            className="folder-btn"
                            onClick={() => handleShowInFolder(result.video_path)}
                            title="在文件夹中显示"
                          >
                            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                            </svg>
                          </button>
                        </div>
                        <div className="match-badge">
                          {getScorePercentage(result.score)}% 匹配
                        </div>
                      </div>
                      <div className="card-info">
                        <div className="card-header">
                          <span className="card-time">
                            {formatTimeRange(result.start_time, result.end_time)}
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
                  )
                })}
              </div>
            </>
          ) : (
            <div className="empty-state">
              <svg className="w-24 h-24 text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              <h3 className="empty-title">未找到相关镜头</h3>
              <p className="empty-text">尝试不同的搜索词或调整筛选条件</p>
            </div>
          )}
        </div>
      </main>

      <aside className="metadata-panel">
        <div className="metadata-header">
          <h3>元数据</h3>
        </div>
        <div className="metadata-content">
          {selectedImage ? (
            <>
              <div className="metadata-section">
                <h4>画面信息</h4>
                <div className="metadata-field">
                  <span className="field-label">时间戳</span>
                  <span className="field-value">
                    {formatTimeRange(selectedImage.start_time, selectedImage.end_time)}
                  </span>
                </div>
                <div className="metadata-field">
                  <span className="field-label">文件路径</span>
                  <span className="field-value filename" title={selectedImage.video}>
                    {selectedImage.video.split(/[\\/]/).pop()}
                  </span>
                </div>
              </div>
              <div className="metadata-section">
                <h4>AI 描述</h4>
                <p className="metadata-description">{selectedImage.description}</p>
              </div>
            </>
          ) : (
            <div className="metadata-empty">
              <p>点击缩略图查看详情</p>
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

export default App
