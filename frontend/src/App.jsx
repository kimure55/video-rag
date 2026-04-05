import React, { useState, useEffect, useRef } from 'react'
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

  useEffect(() => {
    if (processing) {
      progressInterval.current = setInterval(async () => {
        try {
          const resp = await axios.get(`${API_BASE}/process/status`)
          setProgressData(resp.data)
        } catch (e) {
          console.error('获取进度失败', e)
        }
      }, 1000)
    } else {
      if (progressInterval.current) {
        clearInterval(progressInterval.current)
        progressInterval.current = null
      }
      setProgressData(null)
    }
    return () => {
      if (progressInterval.current) {
        clearInterval(progressInterval.current)
      }
    }
  }, [processing])

  const handleSearch = async (e) => {
    if (e) e.preventDefault()
    if (!searchQuery.trim()) return

    setLoading(true)
    try {
      const response = await axios.post(`${API_BASE}/search/`, {
        query: searchQuery,
        top_k: 20
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
      status: 'processing'
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
      setProgressData(null)
    }
  }

  const handleMouseEnter = (result) => {
    setHoveredVideo(result.video_path)
  }

  const handleMouseLeave = () => {
    setHoveredVideo(null)
  }

  const formatTimestamp = (seconds) => {
    const mins = Math.floor(seconds / 60)
    const secs = Math.floor(seconds % 60)
    return `${mins}:${secs.toString().padStart(2, '0')}`
  }

  const formatTimeRange = (start, end) => {
    return `${formatTimestamp(start)} - ${formatTimestamp(end)}`
  }

  const getScorePercentage = (score) => {
    const similarity = Math.max(0, 1 - score)
    return (similarity * 100).toFixed(1)
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
    const filename = framePath.split(/[\\/]/).pop()
    return `${API_BASE}/frames/${filename}`
  }

  const getProgressPercent = () => {
    if (!progressData || progressData.total_videos === 0) return 0
    return Math.round((progressData.current_video_index / progressData.total_videos) * 100)
  }

  return (
    <div className="min-h-screen bg-premiere-dark flex flex-col">
      {selectedImage && (
        <div className="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-8" onClick={() => setSelectedImage(null)}>
          <div className="relative max-w-6xl max-h-full" onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => setSelectedImage(null)}
              className="absolute -top-10 right-0 text-white text-2xl hover:text-gray-300"
            >
              ✕ 关闭
            </button>
            <img
              src={selectedImage.url}
              alt={selectedImage.description}
              className="max-w-full max-h-[80vh] object-contain rounded-lg"
            />
            <div className="mt-4 text-white text-center">
              <p className="text-lg">{selectedImage.description}</p>
              <p className="text-gray-400 text-sm mt-1">{selectedImage.video}</p>
              <p className="text-premiere-accent text-sm">{formatTimeRange(selectedImage.start_time, selectedImage.end_time)}</p>
            </div>
          </div>
        </div>
      )}

      <header className="border-b border-premiere-light bg-premiere-gray">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-2xl font-semibold text-white flex items-center gap-2">
              <svg className="w-8 h-8 text-premiere-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              视频语义检索
            </h1>
          </div>

          <form onSubmit={handleSearch} className="relative">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索视频语义描述... (例如: '日落时弹吉他的人')"
              className="w-full px-6 py-4 bg-premiere-dark border border-premiere-light rounded-lg text-white text-lg placeholder-gray-500 focus:outline-none focus:border-premiere-accent focus:ring-1 focus:ring-premiere-accent transition-colors"
            />
            <button
              type="submit"
              disabled={loading}
              className="absolute right-3 top-1/2 -translate-y-1/2 px-6 py-2 bg-premiere-accent text-white rounded-md font-medium hover:bg-cyan-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  搜索中...
                </span>
              ) : (
                '搜索'
              )}
            </button>
          </form>

          <div className="mt-4 flex items-center gap-4">
            <div className="flex-1 flex items-center gap-3">
              <input
                type="text"
                value={folderPath}
                onChange={(e) => setFolderPath(e.target.value)}
                placeholder="输入视频文件夹路径... (例如: C:\Videos)"
                className="flex-1 px-4 py-2 bg-premiere-dark border border-premiere-light rounded-md text-white placeholder-gray-500 focus:outline-none focus:border-premiere-accent transition-colors text-sm"
              />
              <button
                type="button"
                onClick={handleBrowse}
                className="px-4 py-2 bg-premiere-light text-white rounded-md font-medium hover:bg-premiere-gray border border-premiere-light transition-colors text-sm"
              >
                浏览
              </button>
              <button
                onClick={handleProcess}
                disabled={processing || !folderPath.trim()}
                className="px-5 py-2 bg-green-600 text-white rounded-md font-medium hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm whitespace-nowrap"
              >
                {processing ? '处理中...' : '处理视频'}
              </button>
            </div>
          </div>

          {processing && progressData && (
            <div className="mt-4 bg-premiere-dark rounded-lg p-4 border border-premiere-light">
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm text-white">
                  正在处理：{progressData.current_video || '初始化中...'}
                  {progressData.total_videos > 0 && ` (${progressData.current_video_index}/${progressData.total_videos})`}
                </span>
                <span className="text-sm text-premiere-accent">{getProgressPercent()}%</span>
              </div>
              <div className="w-full bg-premiere-gray rounded-full h-2 overflow-hidden">
                <div
                  className="bg-premiere-accent h-full transition-all duration-300"
                  style={{ width: `${getProgressPercent()}%` }}
                />
              </div>
              {progressData.processed_frames > 0 && (
                <p className="text-xs text-gray-400 mt-2">
                  已处理 {progressData.processed_frames} 帧
                </p>
              )}
            </div>
          )}

          {processStatus && (
            <div className={`mt-3 px-4 py-3 rounded-md text-sm ${processStatus.status === 'success' ? 'bg-green-900/50 text-green-400 border border-green-700' : 'bg-red-900/50 text-red-400 border border-red-700'}`}>
              {processStatus.message}
            </div>
          )}
        </div>
      </header>

      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-center">
              <svg className="w-12 h-12 animate-spin text-premiere-accent mx-auto mb-4" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <p className="text-gray-400">搜索中...</p>
            </div>
          </div>
        ) : results.length > 0 ? (
          <>
            <div className="mb-4 text-gray-400 text-sm">
              找到 {results.length} 个结果
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {results.map((result, index) => (
                <div
                  key={`${result.video_path}-${result.timestamp}-${index}`}
                  className="video-card aspect-video"
                  onMouseEnter={() => handleMouseEnter(result)}
                  onMouseLeave={handleMouseLeave}
                >
                  {hoveredVideo === result.video_path ? (
                    <video
                      ref={(el) => (videoRefs.current[result.video_path] = el)}
                      src={`file://${result.video_path}#t=${result.start_time}`}
                      muted
                      loop
                      playsInline
                      className="thumbnail"
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
                      className="thumbnail cursor-pointer"
                      onClick={() => setSelectedImage({
                        url: getFrameUrl(result.frame_path),
                        description: result.description,
                        video: result.video_path.split(/[\\/]/).pop(),
                        start_time: result.start_time,
                        end_time: result.end_time
                      })}
                      onError={(e) => {
                        e.target.src = `file://${result.frame_path}`
                      }}
                    />
                  )}
                  <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 to-transparent p-3">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs text-premiere-accent font-medium">
                        {result.start_time !== undefined ? formatTimeRange(result.start_time, result.end_time) : formatTimestamp(result.timestamp)}
                      </span>
                      <span className="text-xs text-gray-400">
                        {getScorePercentage(result.score)}% 匹配
                      </span>
                    </div>
                    <p className="text-xs text-gray-300 line-clamp-2">
                      {result.description}
                    </p>
                    <div className="flex items-center justify-between mt-2">
                      <p className="text-xs text-gray-500 truncate flex-1">
                        {result.video_path.split(/[\\/]/).pop()}
                      </p>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          handleShowInFolder(result.video_path)
                        }}
                        className="text-xs text-premiere-accent hover:text-cyan-400 ml-2"
                        title="在文件夹中显示"
                      >
                        📂
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-64 text-center">
            <svg className="w-16 h-16 text-gray-600 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <h3 className="text-lg font-medium text-gray-400 mb-2">暂无结果</h3>
            <p className="text-gray-500 max-w-md">
              请先处理一个视频文件夹，然后使用语义描述进行搜索，例如"弹吉他的人"或"户外森林场景"。
            </p>
          </div>
        )}
      </main>

      <footer className="border-t border-premiere-light py-4 px-6 text-center text-gray-500 text-sm">
        视频语义检索 - 基于 Ollama + ChromaDB
      </footer>
    </div>
  )
}

export default App
