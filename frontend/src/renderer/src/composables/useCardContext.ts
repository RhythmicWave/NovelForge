import { useCardStore } from '@renderer/stores/useCardStore';
import { get } from 'lodash-es';

// A simple regex to capture @mentions
// Format: @CardTypeName:selector.path.to.field
// Example: @角色卡:last.name -> gets the name of the last character card
// Example: @世界观.world_view.world_name -> gets the world name from the (first) worldview card
const MENTION_REGEX = /@([\w\u4e00-\u9fa5]+)(?::(\w+))?(\.[\w.]+)?/g;

export function useCardContext() {
  const cardStore = useCardStore();

  /**
   * Resolves a single mention tag into its string representation.
   * @param cardTypeName The name of the card type (e.g., '角色卡').
   * @param selector The selector for multiple cards (e.g., 'last', 'all').
   * @param path The lodash-style path to the data field.
   * @returns The resolved string content.
   */
  function resolveMention(cardTypeName: string, selector?: string, path?: string): string {
    // Find all cards of the given type
    const matchingCards = cardStore.cards.filter(c => c.card_type.name === cardTypeName);

    if (matchingCards.length === 0) {
      return `[未找到卡片类型: ${cardTypeName}]`;
    }

    let selectedCards: any[] = [];

    // Apply selector logic
    if (selector === 'last') {
      // Sort by creation date or order to find the last one
      const sorted = [...matchingCards].sort((a, b) => b.display_order - a.display_order);
      selectedCards = sorted.length > 0 ? [sorted[0]] : [];
    } else {
      // Default behavior: select all, or just the first if no multi-selector is implied
      // For now, let's default to the first card if no selector is given
      selectedCards = [matchingCards[0]];
    }

    if (selectedCards.length === 0) {
      return `[未找到卡片: ${cardTypeName}:${selector || ''}]`;
    }

    // Extract data based on the path
    return selectedCards.map(card => {
      const targetData = card.content;
      if (!path) {
        // No path, stringify the whole content
        return JSON.stringify(targetData, null, 2);
      }
      // Use lodash.get for safe deep-property access, remove the leading dot from path
      const value = get(targetData, path.substring(1));
      
      if (value === undefined) {
        return `[字段未找到: ${path.substring(1)}]`;
      }
      return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
    }).join('\\n'); // Join multiple values with newline
  }

  /**
   * Parses a context template string and resolves all @mentions.
   * @param template The template string with @mentions.
   * @returns The final string with all mentions replaced by their content.
   */
  function buildContext(template: string): string {
    if (!template) return '';

    return template.replace(MENTION_REGEX, (match, cardTypeName, selector, path) => {
      return resolveMention(cardTypeName, selector, path);
    });
  }

  return {
    buildContext,
  };
} 