-- Detect likely newsletter unsubscribe actions that are present only in the body.
-- The symbol carries no URL or other personalized data; Moolias retrieves the
-- concrete link from Dovecot only for authenticated candidate messages.

local symbol = 'MOOLIAS_BODY_UNSUB'
local needles = {
  'unsubscribe',
  'abbestellen',
  'abmelden',
  'opt out',
  'opt-out',
  'manage preferences',
  'manage email preferences',
}

local function detect_body_unsubscribe(task)
  if not task:has_urls() then
    return false
  end

  local parts = task:get_text_parts()
  if not parts then
    return false
  end

  for _, part in ipairs(parts) do
    local content = part:get_content('content_oneline')
    if content then
      local text = tostring(content):lower()
      for _, needle in ipairs(needles) do
        if text:find(needle, 1, true) then
          return true, needle
        end
      end
    end
  end

  return false
end

rspamd_config:register_symbol({
  name = symbol,
  type = 'normal',
  callback = detect_body_unsubscribe,
  score = 0.0,
  group = 'moolias',
  description = 'Message body contains a likely unsubscribe action',
})
